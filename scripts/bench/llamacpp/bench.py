#!/usr/bin/env python3
"""Benchmark a running llama.cpp service and log results for config iteration.

Measures, via the server's native /completion endpoint (cache_prompt=false):
  - short-context decode speed (median of N runs)
  - prefill speed at several exact prompt sizes (tokens)
  - decode speed at depth (generation after each long prefill)

Each run is appended to results/<service>.jsonl together with the container's
actual CLI args and VRAM/RAM usage, and a comparison table of all recorded
runs is printed at the end.

Usage:
  scripts/bench/llamacpp/bench.py <service-name> [--label baseline]
      [--sizes 2048,8192,32768] [--gen 128] [--runs 3]
"""

import argparse
import datetime
import json
import pathlib
import statistics
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[3]
HERE = pathlib.Path(__file__).resolve().parent
CORPUS_URL = "https://www.gutenberg.org/files/2600/2600-0.txt"


def http_json(url, payload, api_key, timeout):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def load_service(name):
    services = json.loads((ROOT / "services.json").read_text())
    if name not in services:
        sys.exit(f"service '{name}' not found in services.json")
    svc = services[name]
    if svc.get("template_type") != "llamacpp":
        sys.exit(f"service '{name}' is not a llamacpp service")
    return svc


def container_config(name):
    try:
        out = subprocess.run(
            ["docker", "inspect", "--format", "{{json .Config.Cmd}}", name],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        cmd = json.loads(out)
        return " ".join(cmd) if isinstance(cmd, list) else str(cmd)
    except subprocess.CalledProcessError:
        return None


def gpu_mem_mib():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return int(out.splitlines()[0])
    except Exception:
        return None


def host_ram_used_gib():
    try:
        for line in pathlib.Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable"):
                avail_kib = int(line.split()[1])
            if line.startswith("MemTotal"):
                total_kib = int(line.split()[1])
        return round((total_kib - avail_kib) / 1024 / 1024, 1)
    except Exception:
        return None


def get_corpus_tokens(base, api_key, need_tokens):
    corpus = HERE / "data" / "corpus.txt"
    if not corpus.exists():
        corpus.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading corpus to {corpus} ...")
        urllib.request.urlretrieve(CORPUS_URL, corpus)
    text = corpus.read_text(errors="ignore")
    approx_chars = min(len(text), need_tokens * 6)
    resp = http_json(f"{base}/tokenize", {"content": text[:approx_chars]},
                     api_key, timeout=300)
    tokens = resp["tokens"]
    if len(tokens) < need_tokens:
        sys.exit(f"corpus too small: {len(tokens)} tokens, need {need_tokens}")
    return tokens


def completion(base, api_key, prompt_tokens, n_predict, timeout):
    resp = http_json(
        f"{base}/completion",
        {
            "prompt": prompt_tokens,
            "n_predict": n_predict,
            "cache_prompt": False,
            "temperature": 0,
        },
        api_key, timeout,
    )
    return resp["timings"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("service")
    ap.add_argument("--label", default="")
    ap.add_argument("--sizes", default="2048,8192,32768",
                    help="comma-separated prefill sizes in tokens")
    ap.add_argument("--gen", type=int, default=128,
                    help="tokens generated in the short-context decode test")
    ap.add_argument("--runs", type=int, default=3,
                    help="repetitions of the decode test (median reported)")
    ap.add_argument("--depth-gen", type=int, default=64,
                    help="tokens generated after each prefill (decode at depth)")
    ap.add_argument("--timeout", type=int, default=3600)
    args = ap.parse_args()

    svc = load_service(args.service)
    base = f"http://localhost:{svc['port']}"
    api_key = svc["api_key"]
    sizes = [int(s) for s in args.sizes.split(",") if s]

    try:
        with urllib.request.urlopen(f"{base}/health", timeout=5) as r:
            if r.status != 200:
                raise RuntimeError
    except Exception:
        sys.exit(f"service not healthy at {base}/health — is it running?")

    print(f"benchmarking {args.service} at {base}")
    tokens = get_corpus_tokens(base, api_key, max(sizes) if sizes else 512)

    print("warmup ...")
    completion(base, api_key, tokens[:64], 8, args.timeout)

    decode_speeds = []
    for i in range(args.runs):
        t = completion(base, api_key, tokens[:512], args.gen, args.timeout)
        decode_speeds.append(t["predicted_per_second"])
        print(f"  decode run {i + 1}/{args.runs}: "
              f"{t['predicted_per_second']:.1f} t/s")
    decode_tps = statistics.median(decode_speeds)

    prefill = []
    for size in sizes:
        print(f"  prefill {size} tokens ...", flush=True)
        t = completion(base, api_key, tokens[:size], args.depth_gen,
                       args.timeout)
        entry = {
            "n_prompt": t["prompt_n"],
            "pp_tps": round(t["prompt_per_second"], 1),
            "pp_ms": round(t["prompt_ms"], 0),
            "tg_at_depth_tps": round(t["predicted_per_second"], 1),
        }
        prefill.append(entry)
        print(f"    pp {entry['pp_tps']} t/s "
              f"({entry['pp_ms'] / 1000:.1f}s), "
              f"tg@{size}: {entry['tg_at_depth_tps']} t/s")

    record = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "service": args.service,
        "label": args.label,
        "decode_tps": round(decode_tps, 1),
        "decode_runs": [round(x, 1) for x in decode_speeds],
        "prefill": prefill,
        "vram_mib": gpu_mem_mib(),
        "ram_used_gib": host_ram_used_gib(),
        "container_cmd": container_config(args.service),
        "params": svc.get("params"),
    }

    results = HERE / "results" / f"{args.service}.jsonl"
    results.parent.mkdir(parents=True, exist_ok=True)
    with results.open("a") as f:
        f.write(json.dumps(record) + "\n")
    print(f"\nsaved to {results}")

    rows = [json.loads(line) for line in results.read_text().splitlines()]
    all_sizes = sorted({p["n_prompt"] for r in rows for p in r["prefill"]})
    hdr = ["ts", "label", "tg t/s"]
    hdr += [f"pp{s // 1024}k" for s in all_sizes]
    hdr += [f"tg@{s // 1024}k" for s in all_sizes]
    hdr += ["vram MiB"]
    table = [hdr]
    for r in rows:
        by_size = {p["n_prompt"]: p for p in r["prefill"]}
        row = [r["ts"][5:16], r["label"] or "-", f"{r['decode_tps']:.1f}"]
        row += [f"{by_size[s]['pp_tps']:.0f}" if s in by_size else "-"
                for s in all_sizes]
        row += [f"{by_size[s]['tg_at_depth_tps']:.1f}" if s in by_size else "-"
                for s in all_sizes]
        row += [str(r["vram_mib"] or "-")]
        table.append(row)
    widths = [max(len(row[i]) for row in table) for i in range(len(hdr))]
    print()
    for row in table:
        print("  ".join(c.rjust(w) for c, w in zip(row, widths)))


if __name__ == "__main__":
    main()
