#!/usr/bin/env python3
"""Reasoning-level sweep: drive pi at each thinking level and measure reasoning length.

For each (task, level, run) cell this launches:

    pi -p <task> --model <model> --thinking <level> --no-tools \
        --session-dir <per-run scratch dir> ...

parses the session JSONL pi writes for that run, and records the length of
the model's reasoning (thinking) output, the final answer, token usage and
latency. The point is to see whether pi's thinking levels actually change
how much a local (OpenAI-compatible, e.g. llama.cpp) model reasons.

Output (under --out):
    results.csv     one row per cell
    results.json    meta + all rows (full answers)
    summary.md      per-task table of thinking chars / latency / answer head
    answers/        full final answer text per cell
    sessions/       raw pi session JSONL per cell (kept for re-verification)

Stdlib only. Python 3.10+.

Usage:
    python3 sweep.py --model <provider/id> --tasks tasks/a.txt tasks/b.txt \
        --levels off,low,medium,high,xhigh,max --runs 2 --out results/a

Merge several sweep output dirs into one combined report:
    python3 sweep.py merge results/a results/b results/d --out merged
"""

import argparse
import csv
import glob
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_VERSION = "1.0.0"

DEFAULT_LEVELS = "off,low,medium,high,xhigh,max"

DEFAULT_SYSTEM_PROMPT = (
    "You are a careful reasoning engine. Work step by step and verify each "
    "step before moving on. Show your reasoning, then state the final answer "
    "on its own line as 'Answer: ...'."
)

CSV_COLUMNS = [
    "task",
    "level",
    "run",
    "ok",
    "latency_s",
    "thinking_chars",
    "thinking_blocks",
    "answer_chars",
    "out_tokens",
    "prompt_tokens",
    "stop_reason",
    "recorded_level",
    "recorded_model",
    "level_ok",
    "model_ok",
    "answer_head",
    "error",
    "session_file",
]


def sanitize_env(env):
    """Strip PI_* control vars so a child pi cannot inherit the parent
    agent's model/level/session instead of the sweep's flags."""
    return {k: v for k, v in env.items() if not k.startswith("PI_")}


def find_session_file(run_dir):
    files = glob.glob(os.path.join(run_dir, "*.jsonl"))
    if not files:
        raise FileNotFoundError(f"no session .jsonl found in {run_dir}")
    return max(files, key=os.path.getmtime)


def parse_session(path):
    """Aggregate thinking length, answer text and usage from a pi session JSONL."""
    thinking_chars = 0
    thinking_blocks = 0
    answer_chars = 0
    answer_parts = []
    out_tokens = 0
    prompt_tokens = 0
    recorded_level = None
    recorded_provider = None
    recorded_model = None
    assistant_turns = 0
    stop_reasons = []

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            etype = entry.get("type")
            if etype == "thinking_level_change":
                recorded_level = entry.get("thinkingLevel")
            elif etype == "model_change":
                recorded_provider = entry.get("provider")
                recorded_model = entry.get("modelId")
            elif etype == "message":
                msg = entry.get("message") or {}
                if msg.get("role") != "assistant":
                    continue
                assistant_turns += 1
                turn_parts = []
                for block in msg.get("content") or []:
                    btype = block.get("type")
                    if btype == "thinking":
                        thinking_blocks += 1
                        thinking_chars += len(block.get("thinking") or block.get("text") or "")
                    elif btype == "text":
                        turn_parts.append(block.get("text") or "")
                turn_text = "\n".join(turn_parts)
                answer_parts.append(turn_text)
                answer_chars += len(turn_text)
                usage = msg.get("usage") or {}
                out_tokens += int(usage.get("output") or 0)
                prompt_tokens = int(usage.get("input") or 0)
                stop_reasons.append(str(msg.get("stopReason") or ""))

    return {
        "thinking_chars": thinking_chars,
        "thinking_blocks": thinking_blocks,
        "answer_chars": answer_chars,
        "answer_text": answer_parts[-1] if answer_parts else "",
        "out_tokens": out_tokens,
        "prompt_tokens": prompt_tokens,
        "recorded_level": recorded_level,
        "recorded_provider": recorded_provider,
        "recorded_model": recorded_model,
        "assistant_turns": assistant_turns,
        "stop_reason": stop_reasons[-1] if stop_reasons else "",
    }


def verify_model(pi_bin, model):
    """Preflight: confirm pi knows this exact model id, so a typo fails in one
    second with a clean error instead of 12 wasted failed cells."""
    try:
        v = subprocess.run(
            [pi_bin, "--list-models", model, "--offline"],
            capture_output=True,
            text=True,
            timeout=60,
            env=sanitize_env(os.environ),
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"could not run '{pi_bin} --list-models': {e}"
    output = (v.stdout or "") + (v.stderr or "")
    if model in output:
        return ""
    provider, sep, model_id = model.partition("/")
    if sep:
        # table output keeps provider and model in separate columns
        for line in output.splitlines():
            cells = line.split()
            if len(cells) >= 2 and cells[0] == provider and cells[1] == model_id:
                return ""
    return f"model {model!r} not found by 'pi --list-models' (check provider/model id)"


def build_pi_command(pi_bin, model, level, prompt, system_prompt, session_dir):
    return [
        pi_bin,
        "-p",
        prompt,
        "--model",
        model,
        "--thinking",
        level,
        "--system-prompt",
        system_prompt,
        "--no-tools",
        "--no-extensions",
        "--no-skills",
        "--no-prompt-templates",
        "--no-context-files",
        "--offline",
        "--mode",
        "text",
        "--session-dir",
        session_dir,
    ]


def run_cell(pi_bin, model, level, prompt, system_prompt, run_dir, timeout):
    cmd = build_pi_command(pi_bin, model, level, prompt, system_prompt, str(run_dir))
    env = sanitize_env(os.environ)
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(run_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
        latency = time.monotonic() - t0
        return latency, proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired as e:
        latency = time.monotonic() - t0
        stdout = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        return latency, -1, stdout, f"timeout after {timeout}s"


def write_atomic(path, content):
    """Write via temp file + rename so a crash never corrupts results.json
    (which resume depends on)."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def build_csv(rows, extra_columns=()):
    fields = CSV_COLUMNS + list(extra_columns)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fields})
    return buf.getvalue()


def persist(out_dir, meta, rows, extra_columns=()):
    write_atomic(out_dir / "results.csv", build_csv(rows, extra_columns))
    write_atomic(out_dir / "results.json", json.dumps({"meta": meta, "rows": rows}, indent=2))
    write_atomic(out_dir / "summary.md", build_summary(meta, rows))


def fmt_mean(values):
    if not values:
        return "n/a"
    return f"{sum(values) / len(values):.0f}"


def fmt_latency(values):
    if not values:
        return "n/a"
    return f"{sum(values) / len(values):.1f}"


def build_summary(meta, rows):
    lines = []
    lines.append("# Reasoning-level sweep summary")
    lines.append("")
    lines.append(f"- model: `{meta['model']}`")
    lines.append(f"- levels: {', '.join(meta['levels'])}")
    lines.append(f"- runs per cell: {meta['runs']}")
    lines.append(f"- pi version: {meta.get('pi_version', '?')}")
    lines.append(f"- system prompt: {meta.get('system_prompt', '(default)')[:100]}...")
    lines.append(f"- finished: {meta.get('finished', '')}")
    lines.append("")

    tasks = []
    for row in rows:
        if row["task"] not in tasks:
            tasks.append(row["task"])
    levels = meta["levels"]

    for task in tasks:
        lines.append(f"## task: {task}")
        lines.append("")
        lines.append(
            "| level | ok/runs | thinking chars mean | thinking chars min-max "
            "| answer chars mean | out tokens mean | latency s mean |"
        )
        lines.append(
            "|---|---|---|---|---|---|---|"
        )
        for level in levels:
            cell = [r for r in rows if r["task"] == task and r["level"] == level]
            ok = sum(1 for r in cell if r["ok"])
            think = [r["thinking_chars"] for r in cell if r["ok"]]
            ans = [r["answer_chars"] for r in cell if r["ok"]]
            tok = [r["out_tokens"] for r in cell if r["ok"]]
            lat = [r["latency_s"] for r in cell if r["ok"]]
            think_range = f"{min(think)}-{max(think)}" if think else "n/a"
            lines.append(
                f"| {level} | {ok}/{len(cell)} | {fmt_mean(think)} | {think_range} "
                f"| {fmt_mean(ans)} | {fmt_mean(tok)} | "
                f"{fmt_latency(lat)} |"
            )
        lines.append("")

    failed = [r for r in rows if not r["ok"]]
    if failed:
        lines.append("## failed cells")
        lines.append("")
        for r in failed:
            lines.append(f"- {r['task']} / {r['level']} / run {r['run']}: {r['error']}")
        lines.append("")

    truncated = [
        r for r in rows
        if r.get("ok") and r.get("stop_reason") not in ("", "stop", "endTurn")
    ]
    if truncated:
        lines.append("## non-natural stops (truncation / ceiling / abort)")
        lines.append("")
        for r in truncated:
            lines.append(
                f"- {r['task']} / {r['level']} / run {r['run']}: "
                f"stop_reason={r.get('stop_reason')!r} think={r['thinking_chars']}ch "
                f"out_tokens={r['out_tokens']}"
            )
        lines.append("")

    suspicious = [r for r in rows if r.get("ok") and (not r.get("level_ok") or not r.get("model_ok"))]
    if suspicious:
        lines.append("## suspicious cells (ok, but pi did not record the requested level/model)")
        lines.append("")
        for r in suspicious:
            lines.append(
                f"- {r['task']} / {r['level']} / run {r['run']}: "
                f"recorded_level={r['recorded_level']} recorded_model={r['recorded_model']}"
            )
        lines.append("")

    return "\n".join(lines)


def load_previous(out_dir):
    """Resume support: return (previously completed ok rows, previous meta)."""
    prev = out_dir / "results.json"
    if not prev.exists():
        return [], {}
    try:
        with open(prev, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [r for r in data.get("rows", []) if r.get("ok")], data.get("meta", {})
    except (json.JSONDecodeError, OSError):
        return [], {}


def cmd_run(args):
    tasks = []
    for path in args.tasks:
        p = Path(path).resolve()
        if not p.is_file():
            print(f"error: task file not found: {p}", file=sys.stderr)
            return 2
        prompt = p.read_text(encoding="utf-8").strip()
        tasks.append((p.stem, prompt))

    # Absolute paths: pi resolves --session-dir against the child's cwd, and
    # each run's cwd is its own scratch dir, so a relative --out would nest.
    out_dir = Path(args.out).resolve()
    sessions_dir = out_dir / "sessions"
    answers_dir = out_dir / "answers"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    answers_dir.mkdir(parents=True, exist_ok=True)

    levels = [x.strip() for x in args.levels.split(",") if x.strip()]
    system_prompt = args.system_prompt or DEFAULT_SYSTEM_PROMPT

    model_error = verify_model(args.pi, args.model)
    if model_error:
        print(f"error: {model_error}", file=sys.stderr)
        return 2

    pi_version = "?"
    try:
        v = subprocess.run(
            [args.pi, "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            env=sanitize_env(os.environ),
            stdin=subprocess.DEVNULL,
        )
        pi_version = (v.stdout or v.stderr).strip().splitlines()[0] if (v.stdout or v.stderr) else "?"
    except (OSError, subprocess.TimeoutExpired, IndexError):
        pass

    meta = {
        "script_version": SCRIPT_VERSION,
        "model": args.model,
        "levels": levels,
        "runs": args.runs,
        "timeout_s": args.timeout,
        "pi_bin": args.pi,
        "pi_version": pi_version,
        "system_prompt": system_prompt,
        "tasks": [t for t, _ in tasks],
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }

    previous, prev_meta = load_previous(out_dir)
    if previous and prev_meta.get("model") and prev_meta.get("model") != args.model:
        print(
            f"error: {out_dir / 'results.json'} was produced for model "
            f"{prev_meta.get('model')!r}, not {args.model!r}; use a fresh --out",
            file=sys.stderr,
        )
        return 2
    cells_now = {(t, lv, r) for t, _ in tasks for lv in levels for r in range(1, args.runs + 1)}
    rows = [r for r in previous if (r["task"], r["level"], r["run"]) in cells_now]
    done = {(r["task"], r["level"], r["run"]) for r in rows}
    if done:
        print(f"[resume] skipping {len(done)} already-completed cells", file=sys.stderr)

    expected_model_id = args.model.rsplit("/", 1)[-1]
    total_cells = len(tasks) * len(levels) * args.runs
    completed = 0

    for task_id, prompt in tasks:
        for level in levels:
            for run in range(1, args.runs + 1):
                key = (task_id, level, run)
                completed += 1
                label = f"[{task_id}/{level}/r{run}] ({completed}/{total_cells})"
                if key in done:
                    print(f"{label} skipped (already done)", file=sys.stderr)
                    continue

                run_dir = sessions_dir / f"{task_id}__{level}__r{run}"
                run_dir.mkdir(parents=True, exist_ok=True)
                for old in run_dir.glob("*.jsonl"):
                    old.unlink()
                print(f"{label} running ...", file=sys.stderr, flush=True)
                latency, rc, stdout, stderr = run_cell(
                    args.pi, args.model, level, prompt, system_prompt, run_dir, args.timeout
                )

                error = ""
                parsed = None
                session_file = None
                if rc != 0:
                    error = f"exit {rc}: {stderr.strip()[-500:]}"
                try:
                    session_file = find_session_file(str(run_dir))
                    parsed = parse_session(session_file)
                except (FileNotFoundError, OSError, ValueError) as e:
                    error = (error + " | " if error else "") + str(e)

                ok = rc == 0 and parsed is not None and parsed["assistant_turns"] >= 1
                if not ok and rc == 0 and parsed is not None and not error:
                    error = "exit 0 but session has no assistant message"
                row = {
                    "task": task_id,
                    "level": level,
                    "run": run,
                    "ok": ok,
                    "latency_s": round(latency, 1),
                    "thinking_chars": parsed["thinking_chars"] if parsed else 0,
                    "thinking_blocks": parsed["thinking_blocks"] if parsed else 0,
                    "answer_chars": parsed["answer_chars"] if parsed else 0,
                    "out_tokens": parsed["out_tokens"] if parsed else 0,
                    "prompt_tokens": parsed["prompt_tokens"] if parsed else 0,
                    "stop_reason": parsed["stop_reason"] if parsed else "",
                    "recorded_level": parsed["recorded_level"] if parsed else None,
                    "recorded_model": parsed["recorded_model"] if parsed else None,
                    "level_ok": (parsed["recorded_level"] == level) if parsed else False,
                    "model_ok": (parsed["recorded_model"] == expected_model_id) if parsed else False,
                    "answer_head": (parsed["answer_text"][:120].replace("\n", " ") if parsed else ""),
                    "error": error,
                    "session_file": os.path.relpath(session_file, out_dir) if session_file else "",
                    "answer_full": parsed["answer_text"] if parsed else stdout,
                }
                rows.append(row)

                if parsed:
                    (answers_dir / f"{task_id}__{level}__r{run}.txt").write_text(
                        parsed["answer_text"] or "(no text content)", encoding="utf-8"
                    )
                status = "ok" if ok else f"FAIL ({error[:80]})"
                print(
                    f"{label} {status} {latency:.1f}s "
                    f"think={row['thinking_chars']}ch ans={row['answer_chars']}ch",
                    file=sys.stderr,
                    flush=True,
                )
                meta["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                persist(out_dir, meta, rows)

    meta["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    persist(out_dir, meta, rows)
    ok_count = sum(1 for r in rows if r.get("ok"))
    print(f"\nDONE: {ok_count}/{len(rows)} cells ok. out: {out_dir}", file=sys.stderr)
    print(build_summary(meta, rows))
    return 0 if ok_count == len(rows) else 1


def cmd_merge(args):
    rows = []
    metas = []
    for d in args.dirs:
        p = Path(d) / "results.json"
        if not p.exists():
            print(f"merge: missing {p}", file=sys.stderr)
            continue
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        metas.append(data.get("meta", {}))
        for r in data.get("rows", []):
            r = dict(r)
            r["dir"] = str(d)
            rows.append(r)
    if not rows:
        print("merge: no rows found", file=sys.stderr)
        return 1

    levels = []
    for m in metas:
        for lv in m.get("levels", []):
            if lv not in levels:
                levels.append(lv)

    out_dir = Path(args.out).resolve() if args.out else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        merged_meta = {
            "model": metas[0].get("model") if metas else "?",
            "levels": levels,
            "runs": max((m.get("runs", 1) for m in metas), default=1),
            "pi_version": metas[0].get("pi_version", "?") if metas else "?",
            "system_prompt": metas[0].get("system_prompt", "") if metas else "",
            "dirs": [str(d) for d in args.dirs],
            "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        merged_meta["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        persist(out_dir, merged_meta, rows, extra_columns=("dir",))
        print(f"merged {len(rows)} rows from {len(metas)} dirs -> {out_dir}")
    print(build_summary({"model": (metas[0].get("model") if metas else "?"), "levels": levels,
                         "runs": 1, "finished": ""}, rows))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run", help="run the sweep (default)")
    p_run.add_argument("--model", required=True, help="pi model id, e.g. provider/model")
    p_run.add_argument("--tasks", nargs="+", required=True, help="task prompt files")
    p_run.add_argument("--levels", default=DEFAULT_LEVELS, help=f"comma-separated (default {DEFAULT_LEVELS})")
    p_run.add_argument("--runs", type=int, default=2, help="runs per task/level cell (default 2)")
    p_run.add_argument("--out", required=True, help="output directory")
    p_run.add_argument("--timeout", type=int, default=900, help="per-run timeout seconds (default 900)")
    p_run.add_argument("--pi", default="pi", help="pi binary (default: pi on PATH)")
    p_run.add_argument("--system-prompt", default=None, help="override the fixed system prompt")
    p_run.set_defaults(func=cmd_run)

    p_merge = sub.add_parser("merge", help="merge several sweep output dirs")
    p_merge.add_argument("dirs", nargs="+")
    p_merge.add_argument("--out", default=None, help="where to write merged results (optional)")
    p_merge.set_defaults(func=cmd_merge)

    if argv is None:
        argv = list(sys.argv[1:])
    if not argv or argv[0] not in ("run", "merge"):
        argv = ["run", *argv]
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
