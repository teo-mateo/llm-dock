#!/usr/bin/env python3
"""Record each engine's real CLI flag surface, taken from the engine's own image.

The snapshots in dashboard/flag_surfaces/ are what tests/test_flag_surface_guard.py
guards flag_metadata.py against. This script is the refresh procedure: it runs each
image's help printer, parses the option names, and rewrites the snapshot files
atomically. Run it after a pin moves (ARG VLLM_BASE, DS4_COMMIT, NINFER_COMMIT,
TABBYAPI_REF) or after a llama.cpp/ik_llama.cpp image rebuild.

Per-engine facts measured 2026-09-15:
  vllm           serve --help=all REQUIRES --gpus all on the pinned base (v0.24.0-cu129):
                 without a device the parser construction dies in
                 vllm/config/device.py ("Failed to infer device type") before printing.
                 VLLM_TARGET_DEVICE=cpu does NOT work around it on this pin.
  llamacpp       llama-server/llama-bench --help need --gpus all (libcuda.so.1 is
                 loaded before the parser runs); --help exits immediately, no model.
  ds4            ds4-server --help: no GPU, no model.
  ninfer         ninfer-serve --help: needs --gpus all (libcuda), exits immediately.
  tabbyapi       main.py --help: no GPU, no model (argparse prints before model load).

usage: record-flag-surfaces.py [--engine NAME]...
"""

import argparse
import io
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP_DIR = os.path.join(HERE, os.pardir, "dashboard", "flag_surfaces")

# option-line anchor + token regexes, per help format
TOKEN = re.compile(r"^-{1,2}[A-Za-z][\w-]*$")
USAGE_TOKEN = re.compile(r"--[\w-]+")


def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise SystemExit(f"surface extraction failed (rc={r.returncode}): {cmd}\n{r.stderr[-800:]}")
    return r.stdout


def image_id(name):
    r = subprocess.run(
        ["docker", "images", "--format", "{{.ID}}", name],
        capture_output=True, text=True,
    )
    return r.stdout.strip().splitlines()[0] if r.stdout.strip() else None


def option_lines(text, anchor, whole_line=False):
    """Collect option names from lines whose anchor matches, taking the leading
    run of dash tokens on each line (metavars and descriptions never start a token
    with a dash, so the run ends at the first non-matching token). With
    whole_line, every dash token on the line is taken instead - vLLM's option
    lines carry the short-form alias AFTER the metavar (`--x X, -x X`), and no
    vLLM option line puts a dash-leading token anywhere else (checked against the
    pinned-base capture: the only mid-line dash tokens are real aliases)."""
    flags = set()
    for line in text.splitlines():
        if not re.match(anchor, line):
            continue
        if whole_line:
            flags.update(t for t in re.findall(r"-{1,2}[A-Za-z][\w-]*", line) if TOKEN.match(t))
            continue
        started = False
        for tok in re.split(r"[\s,|]+", line):
            if TOKEN.match(tok):
                flags.add(tok)
                started = True
            elif started:
                break
    return flags


def record(engine, template_types, cmd, image, pin, source_of_truth, text):
    if engine == "ninfer":
        flags = set()
        for line in text.splitlines():
            if re.match(r"^\s*(usage:|\[--)", line):
                flags.update(USAGE_TOKEN.findall(line))
    else:
        anchor = {
            "vllm": r"^  -{1,2}[A-Za-z]",
            "llamacpp_server": r"^-{1,2}[A-Za-z]",
            "llamacpp_bench": r"^\s+-{1,2}[A-Za-z]",
            "ds4": r"^\s+-{1,2}[A-Za-z]",
            "tabbyapi": r"^\s+--[A-Za-z]",
        }[engine]
        flags = option_lines(text, anchor, whole_line=engine == "vllm")
        if engine == "tabbyapi":
            for line in text.splitlines():
                if re.match(r"^\s*(usage:|\[--)", line):
                    flags.update(USAGE_TOKEN.findall(line))

    snap = {
        "engine": engine,
        "template_types": template_types,
        "source_command": cmd,
        "build_identity": {
            "image": image,
            "image_id": image_id(image),
            "pin": pin,
            "pin_note": source_of_truth,
        },
        "flags": sorted(flags),
    }
    path = os.path.join(SNAP_DIR, f"{engine}.json")
    fd, tmp = tempfile.mkstemp(dir=SNAP_DIR)
    with os.fdopen(fd, "w") as f:
        json.dump(snap, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    print(f"{engine}: {len(snap['flags'])} flags recorded -> {path}")
    return snap


ENGINES = {
    "vllm": dict(
        cmd="docker run --rm --gpus all --entrypoint vllm llm-dock-vllm serve --help=all",
        image="llm-dock-vllm",
        pin_file="vllm/Dockerfile", pin_arg="VLLM_BASE",
        template_types=["vllm"],
        source="vllm/Dockerfile ARG VLLM_BASE (the wrapper adds nothing to the parser)",
    ),
    "llamacpp_server": dict(
        cmd="docker run --rm --gpus all --entrypoint /llama.cpp/build/bin/llama-server llm-dock-llamacpp:latest --help",
        image="llm-dock-llamacpp:latest",
        pin=None,
        template_types=["llamacpp", "ik_llamacpp"],
        source="no pin - llama.cpp/Dockerfile clones upstream main at build time; "
               "the image_id is the staleness signal",
    ),
    "llamacpp_bench": dict(
        cmd="docker run --rm --gpus all --entrypoint /llama.cpp/build/bin/llama-bench llm-dock-llamacpp:latest --help",
        image="llm-dock-llamacpp:latest",
        pin=None,
        template_types=["llamacpp_bench"],
        source="no pin - same image and build as llamacpp_server",
    ),
    "ds4": dict(
        cmd="docker run --rm --entrypoint /usr/local/bin/ds4-server llm-dock-ds4 --help",
        image="llm-dock-ds4",
        pin_file="ds4/Dockerfile", pin_arg="DS4_COMMIT",
        template_types=["ds4"],
        source="ds4/Dockerfile ARG DS4_COMMIT",
    ),
    "ninfer": dict(
        cmd="docker run --rm --gpus all --entrypoint /usr/local/bin/ninfer-serve llm-dock-ninfer --help",
        image="llm-dock-ninfer",
        pin_file="ninfer/Dockerfile", pin_arg="NINFER_COMMIT",
        template_types=["ninfer"],
        source="ninfer/Dockerfile ARG NINFER_COMMIT",
    ),
    "tabbyapi": dict(
        cmd="docker run --rm llm-dock-tabbyapi --help",
        image="llm-dock-tabbyapi",
        pin_file="tabbyapi/Dockerfile", pin_arg="TABBYAPI_REF",
        template_types=["tabbyapi"],
        source="tabbyapi/Dockerfile ARG TABBYAPI_REF (digest-pinned base)",
    ),
}


def pin_value(spec):
    if spec.get("pin") is not None:
        return spec["pin"]
    if spec.get("pin_file") is None:
        return None
    path = os.path.join(HERE, os.pardir, spec["pin_file"])
    for line in io.open(path):
        if line.startswith(f"ARG {spec['pin_arg']}="):
            return line.strip().split("=", 1)[1]
    raise SystemExit(f"ARG {spec['pin_arg']} not found in {spec['pin_file']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", action="append", choices=sorted(ENGINES))
    args = ap.parse_args()
    only = set(args.engine or []) or set(ENGINES)
    os.makedirs(SNAP_DIR, exist_ok=True)
    for name in sorted(only):
        spec = ENGINES[name]
        print(f"== {name} ==")
        text = run(spec["cmd"])
        spec["pin"] = pin_value(spec)
        snap = record(name, spec["template_types"], spec["cmd"], spec["image"],
                      spec["pin"], spec["source"], text)
    print("done")


if __name__ == "__main__":
    main()
