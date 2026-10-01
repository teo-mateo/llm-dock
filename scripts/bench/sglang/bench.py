#!/usr/bin/env python3
"""Long decode from a BOS seed only, against a running LLM-Dock SGLang service."""

import argparse
import datetime
import json
from pathlib import Path
import statistics
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[3]


def decode(base, key, bos, length, timeout, progress):
    payload = {"input_ids": [bos], "stream": True,
               "sampling_params": {"temperature": 0, "ignore_eos": True,
                                   "max_new_tokens": length}}
    req = urllib.request.Request(base + "/generate", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + key})
    start = time.perf_counter()
    first = last = None
    first_count = count = 0
    points = []
    meta = {}
    next_progress = start + 30
    with urllib.request.urlopen(req, timeout=timeout) as response:
        for raw in response:
            if not raw.startswith(b"data: "):
                continue
            data = raw[6:].strip()
            if data == b"[DONE]":
                break
            event = json.loads(data)
            if "error" in event:
                raise RuntimeError(str(event["error"]))
            meta = event.get("meta_info", meta)
            current = meta.get("completion_tokens", 0)
            now = time.perf_counter()
            if current > count:
                count = current
                last = now
                if first is None:
                    first, first_count = now, count
                points.append((count, now - start))
            if now >= next_progress and first is not None:
                rate = (count - first_count) / (now - first)
                progress(f"  {count}/{length} tokens; decode {rate:.1f} tok/s")
                next_progress = now + 30
    elapsed = time.perf_counter() - start
    if count != length or first is None or last <= first:
        raise RuntimeError(f"Incomplete decode: expected {length}, got {count}; {meta.get('finish_reason')}")
    if meta.get("prompt_tokens") != 1 or meta.get("cached_tokens", 0) != 0:
        raise RuntimeError("Benchmark must have one BOS input token and zero cached tokens")
    # SSE delivers speculative tokens in chunks. Exclude the entire first chunk
    # from both numerator and denominator, instead of pretending it is one token.
    decode_seconds = last - first
    windows = []
    for lower, upper in ((0, 4096), (4096, 8192), (8192, 16384)):
        inside = [(n, t) for n, t in points if lower < n <= min(upper, length)]
        if len(inside) < 2:
            continue
        n0, t0 = inside[0]
        n1, t1 = inside[-1]
        windows.append({"output_range": [lower, min(upper, length)],
                        "measured_tokens": n1 - n0, "seconds": t1 - t0,
                        "decode_tps": (n1 - n0) / (t1 - t0)})
    return {"requested_output_tokens": length, "output_tokens": count,
            "prompt_tokens": 1, "cached_tokens": 0,
            "ttft_seconds": first - start, "total_seconds": elapsed,
            "decode_seconds": decode_seconds, "first_chunk_tokens": first_count,
            "decode_tps": (count - first_count) / decode_seconds,
            "e2e_tps": count / elapsed, "windows": windows,
            "server_meta": meta}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service")
    parser.add_argument("--lengths", default="4096,8192,16384")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cfg = json.loads((ROOT / "services.json").read_text())[args.service]
    if cfg["template_type"] != "sglang":
        parser.error("service must use SGLang")
    if args.runs < 1:
        parser.error("--runs must be positive")
    lengths = [int(x) for x in args.lengths.split(",")]
    if not lengths or any(x < 2 for x in lengths):
        parser.error("--lengths must contain output lengths of at least two tokens")
    path = cfg["model_path"]
    if not path.startswith("/hf-cache/"):
        parser.error("BOS lookup currently requires an /hf-cache/ checkpoint")
    host_path = Path.home() / ".cache/huggingface" / path.removeprefix("/hf-cache/")
    model_cfg = json.loads((host_path / "config.json").read_text())
    bos = model_cfg.get("bos_token_id", model_cfg.get("text_config", {}).get("bos_token_id"))
    if bos is None:
        parser.error("checkpoint has no BOS token")
    base = f"http://127.0.0.1:{cfg['port']}"
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output or Path(__file__).parent / "results" / f"{args.service}-{stamp}.json"
    result = {"service": args.service, "started_at": stamp, "image": cfg.get("image"),
              "model_path": path, "params": cfg["params"], "concurrency": 1,
              "context_tokens": 0, "seed_tokens": 1, "bos_token_id": bos,
              "temperature": 0, "ignore_eos": True, "runs": [], "summary": []}
    output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        temp = output.with_suffix(".tmp")
        temp.write_text(json.dumps(result, indent=2) + "\n")
        temp.replace(output)

    print(f"Service: {args.service}; zero history + one BOS; C=1; greedy; ignore_eos=true", flush=True)
    print("Warmup: 256 tokens (excluded)", flush=True)
    decode(base, cfg["api_key"], bos, 256, args.timeout, lambda _: None)
    save()
    for length in lengths:
        for run in range(1, args.runs + 1):
            print(f"Output {length}, run {run}/{args.runs}", flush=True)
            row = decode(base, cfg["api_key"], bos, length, args.timeout,
                         lambda line: print(line, flush=True))
            row["run"] = run
            result["runs"].append(row)
            save()
            print(f"  done: {row['decode_tps']:.2f} tok/s; TTFT {row['ttft_seconds']:.3f}s; "
                  f"accept {row['server_meta'].get('spec_accept_rate', 0):.1%}", flush=True)
        rows = [r for r in result["runs"] if r["requested_output_tokens"] == length]
        result["summary"].append({"output_tokens": length, "runs": len(rows),
                                  "median_decode_tps": statistics.median(r["decode_tps"] for r in rows),
                                  "min_decode_tps": min(r["decode_tps"] for r in rows),
                                  "max_decode_tps": max(r["decode_tps"] for r in rows),
                                  "median_ttft_seconds": statistics.median(r["ttft_seconds"] for r in rows),
                                  "median_spec_accept_rate": statistics.median(
                                      r["server_meta"].get("spec_accept_rate", 0) for r in rows)})
        save()
    print(json.dumps(result["summary"], indent=2), flush=True)
    print(f"Results: {output.resolve()}", flush=True)


if __name__ == "__main__":
    main()
