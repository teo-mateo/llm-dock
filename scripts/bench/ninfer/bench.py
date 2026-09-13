#!/usr/bin/env python3
"""Benchmark a running NInfer service and log results for config iteration.

NInfer serves OpenAI Chat Completions and reports its own engine-side timings in
every response (`timings`: prefill ms/tokens, decode ms/tokens, draft stats), so
this script reads rates from the server instead of timing HTTP round trips.
Measured, against a **running** service from `services.json` (no model reload):

  - short-context decode speed (median of N runs)
  - prefill speed at several exact prompt sizes (tokens)
  - decode speed at depth (generation after each long prefill)
  - aggregate decode throughput across `--concurrency` lanes

Prompt sizes are exact: the filler is sized with `/v1/messages/count_tokens`, and
a unique suffix per measurement keeps the service's prefix cache from answering a
previous run's prefix (a cache hit would report a prefill that never happened).
The response's `cached_tokens` is recorded so a hit is visible rather than silent.

Each run is appended to `results/<service>.jsonl` with the container's CLI args
and the image's NInfer commit, and a comparison table of all recorded runs prints
at the end.

Usage:
  scripts/bench/ninfer/bench.py <service-name> [--label baseline]
      [--sizes 2048,8192,16384,32768] [--gen 128] [--runs 3]
      [--depth-gen 64] [--concurrency 2]
"""

import argparse
import concurrent.futures
import datetime
import json
import pathlib
import statistics
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[3]
HERE = pathlib.Path(__file__).resolve().parent
CORPUS = ROOT / "scripts" / "bench" / "llamacpp" / "data" / "corpus.txt"


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
    if svc.get("template_type") != "ninfer":
        sys.exit(f"service '{name}' is not a ninfer service")
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


def image_metadata(name):
    try:
        out = subprocess.run(
            ["docker", "inspect", "--format", "{{json .Config.Labels}}", name],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        labels = json.loads(out) or {}
        return {
            "image": subprocess.run(
                ["docker", "inspect", "--format", "{{.Config.Image}}", name],
                capture_output=True, text=True, check=True,
            ).stdout.strip(),
            "ninfer_commit": labels.get("org.llm-dock.ninfer.commit"),
            "build_date": labels.get("org.llm-dock.build.date"),
        }
    except Exception:
        return {}


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


def served_model(base, api_key):
    with urllib.request.urlopen(
        urllib.request.Request(
            f"{base}/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        ),
        timeout=30,
    ) as resp:
        return json.load(resp)["data"][0]["id"]


def count_tokens(base, api_key, model, text, timeout):
    resp = http_json(f"{base}/v1/messages/count_tokens",
                     {"model": model, "messages": [{"role": "user", "content": text}]},
                     api_key, timeout)
    return resp["input_tokens"]


def sized_prompt(base, api_key, model, corpus, size_tokens, nonce, timeout):
    """A prompt of `size_tokens` tokens (within a token or two), unique per nonce."""
    text = corpus[: size_tokens * 5]
    count = count_tokens(base, api_key, model, text + nonce, timeout)
    for _ in range(4):
        if count == size_tokens:
            break
        text = text[: max(1, int(len(text) * size_tokens / count))]
        count = count_tokens(base, api_key, model, text + nonce, timeout)
    return text + nonce


def chat(base, api_key, model, prompt, max_tokens, timeout):
    resp = http_json(
        f"{base}/v1/chat/completions",
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0,
        },
        api_key, timeout,
    )
    return resp["timings"], resp["usage"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("service")
    ap.add_argument("--label", default="")
    ap.add_argument("--sizes", default="2048,8192,16384,32768",
                    help="comma-separated prefill sizes in tokens")
    ap.add_argument("--gen", type=int, default=128,
                    help="tokens generated in the short-context decode test")
    ap.add_argument("--runs", type=int, default=3,
                    help="repetitions of the decode test (median reported)")
    ap.add_argument("--depth-gen", type=int, default=64,
                    help="tokens generated after each prefill (decode at depth)")
    ap.add_argument("--concurrency", type=int, default=2,
                    help="lanes for the aggregate decode test (0 disables)")
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

    model = served_model(base, api_key)
    print(f"benchmarking {args.service} at {base} (served model id: {model})")

    corpus = CORPUS.read_text(errors="ignore")

    print("warmup ...")
    chat(base, api_key, model, "warmup", 8, args.timeout)

    decode_speeds, drafts, accepts = [], 0, 0
    for i in range(args.runs):
        t, _ = chat(base, api_key, model,
                    sized_prompt(base, api_key, model, corpus, 512, f"\nrun {i} ", args.timeout),
                    args.gen, args.timeout)
        decode_speeds.append(t["predicted_per_second"])
        drafts += t.get("draft_n", 0)
        accepts += t.get("draft_n_accepted", 0)
        print(f"  decode run {i + 1}/{args.runs}: {t['predicted_per_second']:.1f} t/s")
    decode_tps = statistics.median(decode_speeds)

    prefill = []
    for i, size in enumerate(sizes):
        print(f"  prefill {size} tokens ...", flush=True)
        prompt = sized_prompt(base, api_key, model, corpus, size, f"\nsuite {i} ", args.timeout)
        t, usage = chat(base, api_key, model, prompt, args.depth_gen, args.timeout)
        cached = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
        entry = {
            "n_prompt": t["prompt_n"],
            "pp_tps": round(t["prompt_per_second"], 1),
            "pp_ms": round(t["prompt_ms"], 0),
            "tg_at_depth_tps": round(t["predicted_per_second"], 1),
            "cached": cached,
        }
        prefill.append(entry)
        print(f"    pp {entry['pp_tps']} t/s ({entry['pp_ms'] / 1000:.1f}s), "
              f"tg@{entry['n_prompt']}: {entry['tg_at_depth_tps']} t/s"
              + ("  [CACHE HIT — prefill not measured]" if cached else ""))

    concurrency = None
    if args.concurrency > 1:
        print(f"  concurrency {args.concurrency} lanes ...", flush=True)
        prompts = [sized_prompt(base, api_key, model, corpus, 512, f"\nlane {i} ", args.timeout)
                   for i in range(args.concurrency)]
        started = datetime.datetime.now()
        with concurrent.futures.ThreadPoolExecutor(args.concurrency) as pool:
            results = list(pool.map(
                lambda p: chat(base, api_key, model, p, args.gen, args.timeout), prompts))
        wall = (datetime.datetime.now() - started).total_seconds()
        rates = [t["predicted_per_second"] for t, _ in results]
        delivered = sum(t["predicted_n"] for t, _ in results)
        concurrency = {
            "lanes": args.concurrency,
            "wall_s": round(wall, 2),
            "aggregate_tps": round(delivered / wall, 1),
            "per_request_tps": [round(r, 1) for r in rates],
        }
        print(f"    {concurrency['aggregate_tps']} t/s aggregate "
              f"({', '.join(f'{r:.0f}' for r in rates)} per request, {wall:.1f}s wall)")

    record = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "service": args.service,
        "label": args.label,
        "model": model,
        "decode_tps": round(decode_tps, 1),
        "decode_runs": [round(x, 1) for x in decode_speeds],
        "acceptance": {
            "drafts": drafts,
            "accepted": accepts,
            "rate": round(accepts / drafts, 3) if drafts else None,
        },
        "prefill": prefill,
        "concurrency": concurrency,
        "vram_mib": gpu_mem_mib(),
        "ram_used_gib": host_ram_used_gib(),
        "container_cmd": container_config(args.service),
        "params": svc.get("params"),
        **image_metadata(args.service),
    }

    results_path = HERE / "results" / f"{args.service}.jsonl"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with results_path.open("a") as f:
        f.write(json.dumps(record) + "\n")
    print(f"\nsaved to {results_path}")

    rows = [json.loads(line) for line in results_path.read_text().splitlines()]
    all_sizes = sorted({p["n_prompt"] for r in rows for p in r["prefill"]})
    hdr = ["ts", "label", "tg t/s", "accept"]
    hdr += [f"pp{s // 1024}k" for s in all_sizes]
    hdr += [f"tg@{s // 1024}k" for s in all_sizes]
    if any(r.get("concurrency") for r in rows):
        hdr += ["C agg t/s"]
    hdr += ["vram MiB"]
    table = [hdr]
    for r in rows:
        by_size = {p["n_prompt"]: p for p in r["prefill"]}
        rate = (r.get("acceptance") or {}).get("rate")
        row = [r["ts"][5:16], r["label"] or "-", f"{r['decode_tps']:.1f}",
               f"{rate * 100:.0f}%" if rate is not None else "-"]
        row += [f"{by_size[s]['pp_tps']:.0f}" if s in by_size else "-" for s in all_sizes]
        row += [f"{by_size[s]['tg_at_depth_tps']:.1f}" if s in by_size else "-"
                for s in all_sizes]
        if any(x.get("concurrency") for x in rows):
            c = r.get("concurrency")
            row += [f"{c['aggregate_tps']:.0f}" if c else "-"]
        row += [str(r["vram_mib"] or "-")]
        table.append(row)
    widths = [max(len(row[i]) for row in table) for i in range(len(hdr))]
    print()
    for row in table:
        print("  ".join(c.rjust(w) for c, w in zip(row, widths)))


if __name__ == "__main__":
    main()
