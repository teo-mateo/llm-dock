"""Unit tests for sweep.py parsing/env helpers. Run: python3 -m pytest test_sweep.py -q"""

import json

import sweep


def make_session(tmp_path, entries):
    p = tmp_path / "session.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return str(p)


def assistant_message(thinking=None, text=None, usage=None, stop_reason="stop"):
    content = []
    if thinking is not None:
        content.append({"type": "thinking", "thinking": thinking, "thinkingSignature": None})
    if text is not None:
        content.append({"type": "text", "text": text})
    return {
        "type": "message",
        "message": {
            "role": "assistant",
            "content": content,
            "usage": usage or {"input": 100, "output": 50, "reasoning": 0},
            "stopReason": stop_reason,
        },
    }


BASE = [
    {"type": "session", "id": "s1"},
    {"type": "model_change", "provider": "prov", "modelId": "m1"},
    {"type": "thinking_level_change", "thinkingLevel": "high"},
    {"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": "q"}]}},
]


def test_parse_basic(tmp_path):
    p = make_session(tmp_path, BASE + [assistant_message(thinking="abc", text="Answer: 76")])
    r = sweep.parse_session(p)
    assert r["thinking_chars"] == 3
    assert r["thinking_blocks"] == 1
    assert r["answer_text"] == "Answer: 76"
    assert r["answer_chars"] == 10
    assert r["out_tokens"] == 50
    assert r["prompt_tokens"] == 100
    assert r["recorded_level"] == "high"
    assert r["recorded_model"] == "m1"
    assert r["assistant_turns"] == 1


def test_parse_multiple_thinking_blocks_and_turns(tmp_path):
    entries = BASE + [
        assistant_message(thinking="one", text="partial"),
        assistant_message(thinking="two", text=None),
        assistant_message(thinking=None, text="final answer"),
    ]
    p = make_session(tmp_path, entries)
    r = sweep.parse_session(p)
    assert r["thinking_chars"] == 6
    assert r["thinking_blocks"] == 2
    assert r["answer_text"] == "final answer"
    assert r["answer_chars"] == len("partial") + len("final answer")
    assert r["assistant_turns"] == 3
    assert r["out_tokens"] == 150


def test_parse_no_thinking(tmp_path):
    p = make_session(tmp_path, BASE + [assistant_message(thinking=None, text="blue")])
    r = sweep.parse_session(p)
    assert r["thinking_chars"] == 0
    assert r["thinking_blocks"] == 0
    assert r["answer_text"] == "blue"


def test_parse_empty_session(tmp_path):
    p = make_session(tmp_path, BASE)
    r = sweep.parse_session(p)
    assert r["assistant_turns"] == 0
    assert r["answer_text"] == ""
    assert r["thinking_chars"] == 0


def test_parse_skips_malformed_lines(tmp_path):
    p = tmp_path / "session.jsonl"
    p.write_text(
        json.dumps(BASE[0]) + "\nnot-json\n" + json.dumps(assistant_message(text="x")) + "\n",
        encoding="utf-8",
    )
    r = sweep.parse_session(str(p))
    assert r["answer_text"] == "x"


def test_find_session_file_missing(tmp_path):
    try:
        sweep.find_session_file(str(tmp_path))
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_sanitize_env_strips_pi_vars():
    env = {
        "PATH": "/bin",
        "PI_MODEL": "a/b",
        "PI_REASONING_LEVEL": "max",
        "PI_SESSION_FILE": "/x.jsonl",
        "OPENROUTER_API_KEY": "keep-me",
        "HOME": "/root",
    }
    out = sweep.sanitize_env(env)
    assert "PI_MODEL" not in out
    assert "PI_REASONING_LEVEL" not in out
    assert "PI_SESSION_FILE" not in out
    assert out["PATH"] == "/bin"
    assert out["OPENROUTER_API_KEY"] == "keep-me"
    assert out["HOME"] == "/root"


def test_build_pi_command_shape():
    cmd = sweep.build_pi_command("pi", "prov/m1", "low", "q", "sp", "/tmp/sess")
    assert cmd[0] == "pi"
    assert "-p" in cmd and "q" in cmd
    assert cmd[cmd.index("--model") + 1] == "prov/m1"
    assert cmd[cmd.index("--thinking") + 1] == "low"
    assert cmd[cmd.index("--system-prompt") + 1] == "sp"
    assert "--no-tools" in cmd
    assert cmd[cmd.index("--session-dir") + 1] == "/tmp/sess"
    assert "--no-context-files" in cmd


def test_summary_renders_all_levels(tmp_path):
    rows = []
    for level in ["off", "low", "high"]:
        for run in (1, 2):
            rows.append({
                "task": "a", "level": level, "run": run, "ok": True,
                "latency_s": 10.0 + run, "thinking_chars": 100 * (level != "off"),
                "thinking_blocks": 1, "answer_chars": 20, "out_tokens": 30,
                "prompt_tokens": 100, "recorded_level": level, "recorded_model": "m",
                "level_ok": True, "model_ok": True, "answer_head": "x", "error": "",
                "session_file": "s.jsonl", "answer_full": "x",
            })
    rows.append({
        "task": "a", "level": "high", "run": 3, "ok": False, "latency_s": 1.0,
        "thinking_chars": 0, "thinking_blocks": 0, "answer_chars": 0, "out_tokens": 0,
        "prompt_tokens": 0, "recorded_level": None, "recorded_model": None,
        "level_ok": False, "model_ok": False, "answer_head": "",
        "error": "exit 1: boom", "session_file": "", "answer_full": "",
    })
    meta = {"model": "prov/m1", "levels": ["off", "low", "high"], "runs": 2, "pi_version": "0.84.1",
            "system_prompt": "sp", "finished": "now"}
    s = sweep.build_summary(meta, rows)
    assert "| off | 2/2 | 0 | 0-0" in s
    assert "| low | 2/2 | 100 | 100-100" in s
    assert "| high | 2/3 | 100 | 100-100" in s
    assert "a / high / run 3: exit 1: boom" in s


def test_resume_loads_only_ok_cells(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    rows = [
        {"task": "a", "level": "off", "run": 1, "ok": True},
        {"task": "a", "level": "off", "run": 2, "ok": False},
    ]
    (out / "results.json").write_text(json.dumps({"meta": {"model": "p/m"}, "rows": rows}), encoding="utf-8")
    prev, meta = sweep.load_previous(out)
    assert len(prev) == 1
    assert prev[0]["ok"] is True
    assert meta["model"] == "p/m"


def test_load_previous_corrupt_file(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "results.json").write_text("{not json", encoding="utf-8")
    prev, meta = sweep.load_previous(out)
    assert prev == []
    assert meta == {}


def test_parse_captures_stop_reason(tmp_path):
    p = make_session(tmp_path, BASE + [assistant_message(text="x", stop_reason="length")])
    assert sweep.parse_session(p)["stop_reason"] == "length"


def test_summary_flags_non_natural_stop(tmp_path):
    meta = {"model": "p/m", "levels": ["off"], "runs": 1, "pi_version": "x", "system_prompt": "s"}
    rows = [{
        "task": "t", "level": "off", "run": 1, "ok": True, "latency_s": 1.0,
        "thinking_chars": 10, "thinking_blocks": 1, "answer_chars": 5, "out_tokens": 32768,
        "prompt_tokens": 100, "stop_reason": "length", "recorded_level": "off",
        "recorded_model": "m", "level_ok": True, "model_ok": True,
        "answer_head": "x", "error": "", "session_file": "",
    }]
    out = sweep.build_summary(meta, rows)
    assert "non-natural stops" in out
    assert "stop_reason='length'" in out


def test_parse_truncated_final_line_skipped(tmp_path):
    full = json.dumps(assistant_message(text="x"))
    p = tmp_path / "s.jsonl"
    p.write_text(json.dumps(BASE[0]) + "\n" + full[: len(full) // 2] + "\n", encoding="utf-8")
    r = sweep.parse_session(str(p))
    assert r["assistant_turns"] == 0
    assert r["thinking_chars"] == 0


def test_parse_nonnumeric_usage_raises(tmp_path):
    entries = BASE + [assistant_message(text="x", usage={"input": "ten", "output": "twenty"})]
    p = make_session(tmp_path, entries)
    try:
        sweep.parse_session(p)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_find_session_picks_newest(tmp_path):
    import os

    old = tmp_path / "old.jsonl"
    new = tmp_path / "new.jsonl"
    old.write_text("x", encoding="utf-8")
    new.write_text("x", encoding="utf-8")
    os.utime(old, (1000, 1000))
    os.utime(new, (2000, 2000))
    assert sweep.find_session_file(str(tmp_path)) == str(new)


FAKE_PI = """#!/usr/bin/env python3
import json, os, sys, time
argv = sys.argv[1:]
if "--version" in argv:
    print("0.0.0-fake")
    sys.exit(0)
if "--list-models" in argv:
    print("p/m")  # the fake registry only knows p/m
    sys.exit(0)

def get(flag):
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            return argv[i + 1]
    return None

sess = get("--session-dir")
level = get("--thinking")
BEHAVIOR
os.makedirs(sess, exist_ok=True)
with open(os.path.join(sess, f"fake-{level}.jsonl"), "w") as f:
    f.write(json.dumps({"type": "session", "id": "x"}) + "\\n")
    f.write(json.dumps({"type": "model_change", "provider": "p", "modelId": "m"}) + "\\n")
    f.write(json.dumps({"type": "thinking_level_change", "thinkingLevel": level}) + "\\n")
    think = "t" * 100 if level != "off" else ""
    content = []
    if think:
        content.append({"type": "thinking", "thinking": think})
    content.append({"type": "text", "text": "Answer: 1"})
    f.write(json.dumps({"type": "message", "message": {
        "role": "assistant", "content": content,
        "usage": {"input": 10, "output": 40}}}) + "\\n")
"""

FAKE_PI_EMPTY = """#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
if "--version" in argv:
    print("0.0.0-fake")
    sys.exit(0)
if "--list-models" in argv:
    print("p/m")
    sys.exit(0)
sess = argv[argv.index("--session-dir") + 1]
os.makedirs(sess, exist_ok=True)
with open(os.path.join(sess, "fake-empty.jsonl"), "w") as f:
    f.write(json.dumps({"type": "session", "id": "x"}) + "\\n")
"""


def write_fake_pi(tmp_path, name, behavior="pass", empty=False):
    body = FAKE_PI_EMPTY if empty else FAKE_PI.replace("BEHAVIOR", behavior)
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    p.chmod(0o755)
    return str(p)


def write_task(tmp_path, text="q"):
    p = tmp_path / "task.txt"
    p.write_text(text, encoding="utf-8")
    return str(p)


def run_sweep(tmp_path, out, levels="off,low", runs=1, timeout=10, model="p/m", extra=None):
    import sweep as s

    argv = [
        "--pi", write_fake_pi(tmp_path, "pi_ok.py"), "--model", model,
        "--tasks", write_task(tmp_path), "--levels", levels,
        "--runs", str(runs), "--out", str(out), "--timeout", str(timeout),
    ]
    if extra:
        argv.extend(extra)
    return s.main(argv)


def test_run_end_to_end_ok(tmp_path):
    import csv as csvmod

    out = tmp_path / "out"
    rc = run_sweep(tmp_path, out)
    assert rc == 0
    data = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert len(data["rows"]) == 2
    by_level = {r["level"]: r for r in data["rows"]}
    assert by_level["off"]["ok"] and by_level["off"]["thinking_chars"] == 0
    assert by_level["low"]["ok"] and by_level["low"]["thinking_chars"] == 100
    assert all(r["level_ok"] and r["model_ok"] for r in data["rows"])
    with open(out / "results.csv", encoding="utf-8") as f:
        csv_rows = list(csvmod.DictReader(f))
    assert len(csv_rows) == 2
    assert set(csv_rows[0].keys()) == set(sweep.CSV_COLUMNS)
    assert (out / "summary.md").exists()
    assert (out / "answers" / "task__low__r1.txt").read_text(encoding="utf-8") == "Answer: 1"


def test_run_failed_pi_cell(tmp_path):
    out = tmp_path / "out"
    pi = write_fake_pi(tmp_path, "pi_fail.py", behavior="sys.exit(1)")
    rc = sweep.main([
        "run", "--pi", pi, "--model", "p/m", "--tasks", write_task(tmp_path),
        "--levels", "off", "--runs", "1", "--out", str(out),
    ])
    assert rc == 1
    data = json.loads((out / "results.json").read_text(encoding="utf-8"))
    row = data["rows"][0]
    assert row["ok"] is False
    assert "exit 1" in row["error"]


def test_run_timeout_cell(tmp_path):
    out = tmp_path / "out"
    pi = write_fake_pi(tmp_path, "pi_sleep.py", behavior="time.sleep(30)")
    rc = sweep.main([
        "run", "--pi", pi, "--model", "p/m", "--tasks", write_task(tmp_path),
        "--levels", "off", "--runs", "1", "--out", str(out), "--timeout", "1",
    ])
    assert rc == 1
    data = json.loads((out / "results.json").read_text(encoding="utf-8"))
    row = data["rows"][0]
    assert row["ok"] is False
    assert "timeout" in row["error"]


def test_run_empty_session_not_ok(tmp_path):
    out = tmp_path / "out"
    pi = write_fake_pi(tmp_path, "pi_empty.py", empty=True)
    rc = sweep.main([
        "run", "--pi", pi, "--model", "p/m", "--tasks", write_task(tmp_path),
        "--levels", "off", "--runs", "1", "--out", str(out),
    ])
    assert rc == 1
    data = json.loads((out / "results.json").read_text(encoding="utf-8"))
    row = data["rows"][0]
    assert row["ok"] is False
    assert "no assistant message" in row["error"]


def test_run_resume_skips_done_cells(tmp_path):
    out = tmp_path / "out"
    assert run_sweep(tmp_path, out) == 0
    # second run: same out dir, same config -> all cells skipped, still rc 0
    assert run_sweep(tmp_path, out) == 0
    data = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert len(data["rows"]) == 2


def test_run_resume_aborts_on_model_change(tmp_path):
    out = tmp_path / "out"
    out.mkdir(parents=True)
    stale_row = {"task": "task", "level": "off", "run": 1, "ok": True, "latency_s": 1,
                 "thinking_chars": 0, "thinking_blocks": 0, "answer_chars": 1, "out_tokens": 1,
                 "prompt_tokens": 1, "recorded_level": "off", "recorded_model": "m",
                 "level_ok": True, "model_ok": True, "answer_head": "x", "error": "",
                 "session_file": "", "answer_full": "x"}
    (out / "results.json").write_text(
        json.dumps({"meta": {"model": "other/m"}, "rows": [stale_row]}), encoding="utf-8"
    )
    rc = run_sweep(tmp_path, out)
    assert rc == 2


def test_run_stale_session_file_cleaned(tmp_path):
    out = tmp_path / "out"
    stale_dir = out / "sessions" / "task__low__r1"
    stale_dir.mkdir(parents=True)
    (stale_dir / "stale.jsonl").write_text(
        json.dumps({"type": "message", "message": {
            "role": "assistant",
            "content": [{"type": "thinking", "thinking": "x" * 9999}]}}) + "\n",
        encoding="utf-8",
    )
    assert run_sweep(tmp_path, out) == 0
    data = json.loads((out / "results.json").read_text(encoding="utf-8"))
    low = [r for r in data["rows"] if r["level"] == "low"][0]
    assert low["thinking_chars"] == 100, "stale session thinking leaked into the measurement"


def test_run_passes_devnull_stdin(tmp_path, monkeypatch):
    """A pi child must never inherit the sweep's stdin: with an open pipe/socket
    stdin, pi blocks reading it forever (observed hang in the wild)."""
    import subprocess as sp

    seen = []
    real_run = sp.run

    def spy(cmd, **kwargs):
        if isinstance(cmd, list) and cmd and cmd[0].endswith("pi_stdin.py"):
            seen.append(kwargs.get("stdin"))
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(sweep.subprocess, "run", spy)
    out = tmp_path / "out"
    rc = sweep.main([
        "run", "--pi", write_fake_pi(tmp_path, "pi_stdin.py"), "--model", "p/m",
        "--tasks", write_task(tmp_path), "--levels", "off", "--runs", "1",
        "--out", str(out),
    ])
    assert rc == 0
    assert seen, "sweep never invoked the pi binary"
    assert all(s is sp.DEVNULL for s in seen), seen


def test_run_preflight_rejects_unknown_model(tmp_path):
    out = tmp_path / "out"
    rc = sweep.main([
        "run", "--pi", write_fake_pi(tmp_path, "pi_ok.py"), "--model", "p/wrong-model",
        "--tasks", write_task(tmp_path), "--levels", "off", "--runs", "1",
        "--out", str(out),
    ])
    assert rc == 2
    assert not (out / "results.json").exists()


def test_run_missing_task_file_clean_error(tmp_path):
    out = tmp_path / "out"
    rc = sweep.main([
        "run", "--pi", write_fake_pi(tmp_path, "pi_ok.py"), "--model", "p/m",
        "--tasks", str(tmp_path / "nope.txt"), "--levels", "off", "--runs", "1",
        "--out", str(out),
    ])
    assert rc == 2
    assert not out.exists()


def test_merge_combines_dirs(tmp_path):
    d1, d2 = tmp_path / "r1", tmp_path / "r2"
    for d, task in ((d1, "a"), (d2, "b")):
        d.mkdir()
        (d / "results.json").write_text(json.dumps({
            "meta": {"model": "p/m", "levels": ["off"], "runs": 1},
            "rows": [{"task": task, "level": "off", "run": 1, "ok": True, "latency_s": 1,
                      "thinking_chars": 5, "thinking_blocks": 1, "answer_chars": 2,
                      "out_tokens": 3, "prompt_tokens": 9, "recorded_level": "off",
                      "recorded_model": "m", "level_ok": True, "model_ok": True,
                      "answer_head": "x", "error": "", "session_file": "s", "answer_full": "x"}],
        }), encoding="utf-8")
    m = tmp_path / "m"
    rc = sweep.main(["merge", str(d1), str(d2), "--out", str(m)])
    assert rc == 0
    data = json.loads((m / "results.json").read_text(encoding="utf-8"))
    assert len(data["rows"]) == 2
    assert {r["dir"] for r in data["rows"]} == {str(d1), str(d2)}
    import csv as csvmod

    with open(m / "results.csv", encoding="utf-8") as f:
        csv_rows = list(csvmod.DictReader(f))
    assert len(csv_rows) == 2
    assert "dir" in csv_rows[0]


def test_chat_kwargs_variants():
    import api_control
    assert api_control.chat_kwargs("none") == {"enable_thinking": False, "reasoning_effort": "none"}
    assert api_control.chat_kwargs("low") == {"enable_thinking": True, "reasoning_effort": "low"}
    assert api_control.chat_kwargs("xhigh") == {"enable_thinking": True, "reasoning_effort": "xhigh"}
    assert api_control.chat_kwargs("high") == {"enable_thinking": True, "reasoning_effort": "high"}
    try:
        api_control.chat_kwargs("bogus")
        assert False, "expected ValueError"
    except ValueError:
        pass


def _start_fake_server():
    """Fake OpenAI-compatible server routing on reasoning_effort in the body."""
    import http.server
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            req = json.loads(body)
            effort = req["chat_template_kwargs"]["reasoning_effort"]
            if effort == "none":
                payload = {"choices": [{"finish_reason": "stop", "message": {
                    "role": "assistant", "content": "Answer: blue",
                    "reasoning_content": ""}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
                self._send(200, json.dumps(payload).encode())
            elif effort == "xhigh":
                payload = {"choices": [{"finish_reason": "length", "message": {
                    "role": "assistant", "content": "partial",
                    "reasoning_content": "x" * 1000}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 9999}}
                self._send(200, json.dumps(payload).encode())
            elif effort == "low":
                self._send(200, b"<html>not json</html>",
                           content_type="text/html")
            else:
                self._send(500, b"boom")

        def _send(self, code, body, content_type="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/v1"


def test_api_control_post_completion_parses_reasoning(tmp_path):
    import api_control

    server, base_url = _start_fake_server()
    try:
        res = api_control.post_completion(
            base_url, "k", "m", "q", api_control.chat_kwargs("none"), 100, 10
        )
        assert res["reasoning_chars"] == 0
        assert res["answer_text"] == "Answer: blue"
        assert res["finish_reason"] == "stop"
        res2 = api_control.post_completion(
            base_url, "k", "m", "q", api_control.chat_kwargs("xhigh"), 100, 10
        )
        assert res2["reasoning_chars"] == 1000
        assert res2["finish_reason"] == "length"
        try:
            api_control.post_completion(
                base_url, "k", "m", "q", api_control.chat_kwargs("medium"), 100, 10
            )
            assert False, "expected HTTPError"
        except Exception as e:
            assert "500" in str(e)
    finally:
        server.shutdown()


def test_api_control_main_loop_records_failures_and_truncation(tmp_path):
    import api_control

    server, base_url = _start_fake_server()
    task = tmp_path / "task.txt"
    task.write_text("q", encoding="utf-8")
    out = tmp_path / "out"
    try:
        rc = api_control.main([
            "--base-url", base_url, "--model", "m", "--api-key", "k",
            "--task", str(task), "--variants", "none,low,medium,xhigh",
            "--runs", "1", "--out", str(out),
        ])
    finally:
        server.shutdown()
    assert rc == 1  # 2 of 4 failed
    data = json.loads((out / "results.json").read_text(encoding="utf-8"))
    by_variant = {r["variant"]: r for r in data["rows"]}
    assert by_variant["none"]["ok"] is True
    assert by_variant["low"]["ok"] is False and "JSONDecodeError" in by_variant["low"]["error"]
    assert by_variant["medium"]["ok"] is False
    assert "500" in by_variant["medium"]["error"]
    assert by_variant["xhigh"]["ok"] is True
    assert by_variant["xhigh"]["finish_reason"] == "length"
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "truncated runs" in summary
