#!/usr/bin/env python3
"""Direct-API control for the reasoning-level sweep.

Bypasses pi entirely: POSTs the same tasks straight to an OpenAI-compatible
server (llama.cpp) using exactly the chat_template_kwargs that pi's
"chat-template" thinking format sends for each pi level. This answers the
question the pi sweep cannot on its own: is the server honoring the
reasoning_effort strings, or only the enable_thinking on/off toggle?

Variant -> chat_template_kwargs (mirrors pi's buildChatTemplateValues for a
model with thinkingLevelMap off->"none", low->"low", medium->"medium",
high/xhigh/max->"xhigh"):

    none    {"enable_thinking": false, "reasoning_effort": "none"}
    low     {"enable_thinking": true,  "reasoning_effort": "low"}
    medium  {"enable_thinking": true,  "reasoning_effort": "medium"}
    xhigh   {"enable_thinking": true,  "reasoning_effort": "xhigh"}

Stdlib only.

Usage:
    API_KEY=... python3 api_control.py \
        --base-url http://localhost:3329/v1 \
        --model llamacpp-qwen3-8-27b-q8kxl \
        --task tasks/a.txt \
        --variants none,low,medium,xhigh --runs 3 --out results/api-control
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SCRIPT_VERSION = "1.0.0"

DEFAULT_SYSTEM_PROMPT = (
    "You are a careful reasoning engine. Work step by step and verify each "
    "step before moving on. Show your reasoning, then state the final answer "
    "on its own line as 'Answer: ...'."
)

VARIANTS = {
    "none": {"enable_thinking": False, "reasoning_effort": "none"},
    "low": {"enable_thinking": True, "reasoning_effort": "low"},
    "medium": {"enable_thinking": True, "reasoning_effort": "medium"},
    "high": {"enable_thinking": True, "reasoning_effort": "high"},
    "xhigh": {"enable_thinking": True, "reasoning_effort": "xhigh"},
}

CSV_COLUMNS = [
    "task", "variant", "run", "ok", "latency_s",
    "reasoning_chars", "answer_chars", "out_tokens", "prompt_tokens",
    "finish_reason", "answer_head", "error",
]


def chat_kwargs(variant):
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}; known: {sorted(VARIANTS)}")
    return dict(VARIANTS[variant])


def write_atomic(path, content):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def build_csv(rows):
    import io

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in CSV_COLUMNS})
    return buf.getvalue()


def post_completion(base_url, api_key, model, prompt, kwargs, max_tokens, timeout):
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "stream": False,
        "chat_template_kwargs": kwargs,
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    latency = time.monotonic() - t0
    choice = data["choices"][0]
    message = choice["message"]
    usage = data.get("usage") or {}
    reasoning = message.get("reasoning_content") or message.get("reasoning") or ""
    return {
        "latency_s": round(latency, 1),
        "reasoning_chars": len(reasoning),
        "answer_chars": len(message.get("content") or ""),
        "out_tokens": int(usage.get("completion_tokens") or 0),
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "finish_reason": choice.get("finish_reason") or "",
        "reasoning_text": reasoning,
        "answer_text": message.get("content") or "",
    }


def build_summary(meta, rows):
    lines = []
    lines.append("# Direct-API control summary")
    lines.append("")
    lines.append(f"- server: {meta['base_url']}  model: `{meta['model']}`")
    lines.append(f"- runs per variant: {meta['runs']}")
    lines.append(f"- finished: {meta.get('finished', '')}")
    lines.append("")
    tasks = []
    for row in rows:
        if row["task"] not in tasks:
            tasks.append(row["task"])
    for task in tasks:
        lines.append(f"## task: {task}")
        lines.append("")
        lines.append("| variant | ok/runs | reasoning chars mean | reasoning chars min-max | answer chars mean | out tokens mean | latency s mean |")
        lines.append("|---|---|---|---|---|---|---|")
        for variant in meta["variants"]:
            cell = [r for r in rows if r["task"] == task and r["variant"] == variant]
            ok = sum(1 for r in cell if r["ok"])
            think = [r["reasoning_chars"] for r in cell if r["ok"]]
            ans = [r["answer_chars"] for r in cell if r["ok"]]
            tok = [r["out_tokens"] for r in cell if r["ok"]]
            lat = [r["latency_s"] for r in cell if r["ok"]]
            rng = f"{min(think)}-{max(think)}" if think else "n/a"
            mean = (lambda v: f"{sum(v) / len(v):.0f}" if v else "n/a")
            lines.append(
                f"| {variant} | {ok}/{len(cell)} | {mean(think)} | {rng} "
                f"| {mean(ans)} | {mean(tok)} | {mean(lat)} |"
            )
        lines.append("")
    truncated = [r for r in rows if r.get("finish_reason") == "length"]
    if truncated:
        lines.append("## truncated runs (hit --max-tokens; reasoning_chars are lower bounds)")
        lines.append("")
        for r in truncated:
            lines.append(f"- {r['task']} / {r['variant']} / run {r['run']}: {r['reasoning_chars']} chars")
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", required=True, help="e.g. http://localhost:3329/v1")
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-key", default=os.environ.get("API_KEY", ""))
    parser.add_argument("--task", action="append", required=True, help="task prompt file (repeatable)")
    parser.add_argument("--variants", default="none,low,medium,xhigh")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--out", required=True, help="output directory")
    args = parser.parse_args(argv)

    if not args.api_key:
        print("error: --api-key or API_KEY env var required", file=sys.stderr)
        return 2

    out_dir = Path(args.out)
    answers_dir = out_dir / "answers"
    answers_dir.mkdir(parents=True, exist_ok=True)

    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    for v in variants:
        chat_kwargs(v)

    tasks = []
    for path in args.task:
        p = Path(path)
        tasks.append((p.stem, p.read_text(encoding="utf-8").strip()))

    meta = {
        "script_version": SCRIPT_VERSION,
        "base_url": args.base_url,
        "model": args.model,
        "variants": variants,
        "runs": args.runs,
        "max_tokens": args.max_tokens,
        "tasks": [t for t, _ in tasks],
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }

    rows = []
    total = len(tasks) * len(variants) * args.runs
    done = 0
    for task_id, prompt in tasks:
        for variant in variants:
            for run in range(1, args.runs + 1):
                done += 1
                label = f"[{task_id}/{variant}/r{run}] ({done}/{total})"
                try:
                    res = post_completion(
                        args.base_url, args.api_key, args.model, prompt,
                        chat_kwargs(variant), args.max_tokens, args.timeout,
                    )
                    row = {
                        "task": task_id, "variant": variant, "run": run, "ok": True,
                        "latency_s": res["latency_s"], "reasoning_chars": res["reasoning_chars"],
                        "answer_chars": res["answer_chars"], "out_tokens": res["out_tokens"],
                        "prompt_tokens": res["prompt_tokens"],
                        "finish_reason": res["finish_reason"],
                        "answer_head": res["answer_text"][:120].replace("\n", " "),
                        "error": "",
                        "answer_full": res["answer_text"],
                        "reasoning_full": res["reasoning_text"],
                    }
                    status = "ok"
                except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError, TimeoutError, OSError) as e:
                    row = {
                        "task": task_id, "variant": variant, "run": run, "ok": False,
                        "latency_s": 0, "reasoning_chars": 0, "answer_chars": 0,
                        "out_tokens": 0, "prompt_tokens": 0, "finish_reason": "", "answer_head": "",
                        "error": f"{type(e).__name__}: {e}",
                        "answer_full": "", "reasoning_full": "",
                    }
                    status = f"FAIL ({row['error'][:80]})"
                rows.append(row)
                (answers_dir / f"{task_id}__{variant}__r{run}.txt").write_text(
                    f"REASONING ({row['reasoning_chars']} chars):\n{row['reasoning_full']}\n\n"
                    f"ANSWER ({row['answer_chars']} chars):\n{row['answer_full']}\n",
                    encoding="utf-8",
                )
                print(
                    f"{label} {status} {row['latency_s']}s "
                    f"think={row['reasoning_chars']}ch ans={row['answer_chars']}ch",
                    file=sys.stderr,
                    flush=True,
                )
                meta["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                write_atomic(out_dir / "results.csv", build_csv(rows))
                write_atomic(out_dir / "results.json", json.dumps({"meta": meta, "rows": rows}, indent=2))
                write_atomic(out_dir / "summary.md", build_summary(meta, rows))

    ok_count = sum(1 for r in rows if r["ok"])
    print(f"\nDONE: {ok_count}/{len(rows)} ok. out: {out_dir}", file=sys.stderr)
    print(build_summary(meta, rows))
    return 0 if ok_count == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
