"""Container entrypoint for llm-dock's Maya engine.

Turns the compose argv into the run config Maya's ``serve/server.py`` reads
(the JSON ``maya.py`` would otherwise write), then execs the server.

    launcher.py --pack <pack dir> --model-name <id> [server knobs] [engine flags]

Launcher knobs are parsed here; every other argument is passed through to the
engine in order, so engine flags need no table in this file.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

MAYA_ROOT = Path(os.environ.get("MAYA_ROOT", "/opt/maya"))
STATE_DIR = Path(os.environ.get("MAYA_STATE_DIR", "/maya-state"))

# The pack's own files say which engine reads it: maya-ds4 writes ds4.txt, the
# GLM packer writes index.txt. top_p is each family's maya.py default.
FAMILIES = {
    "deepseek": {"exe": "build/maya-ds4", "pack_flag": "--pack", "top_p": 1.0},
    "glm": {"exe": "build/maya", "pack_flag": "--glm-pack", "top_p": 0.95},
}

# Engine flags the launcher owns: the pack is model_path, and --serve is how
# server.py starts the engine itself.
RESERVED_ENGINE_FLAGS = {"--pack", "--glm-pack", "--serve"}


def pack_family(pack: Path) -> str:
    if (pack / "ds4.txt").is_file():
        return "deepseek"
    if (pack / "index.txt").is_file():
        return "glm"
    raise SystemExit(f"[llm-dock] {pack} is not a Maya pack (no ds4.txt or index.txt)")


def _parser() -> argparse.ArgumentParser:
    # allow_abbrev=False: an engine flag must never prefix-match a launcher knob
    # (`--model` would otherwise be read as --model-name).
    p = argparse.ArgumentParser(prog="maya-launcher", allow_abbrev=False)
    p.add_argument("--pack", required=True)
    p.add_argument("--model-name", required=True)
    p.add_argument("--api-key", default="")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--gpu", default="0")
    p.add_argument("--sampling-temperature", type=float, default=1.0)
    p.add_argument("--sampling-top-p", type=float)
    p.add_argument("--reasoning-effort", default="high")
    p.add_argument("--thinking-budget", type=int)
    p.add_argument("--engine-ready-s", type=int, default=3600)
    p.add_argument("--idle-unload", type=float)
    return p


def _effort(value: str):
    return int(value) if value.isdigit() else value


def build_config(argv: List[str], state_dir: Path = STATE_DIR,
                 maya_root: Path = MAYA_ROOT) -> Tuple[Dict, str]:
    """The server's run config, and the API key the server is started with."""
    args, engine_args = _parser().parse_known_args(argv)
    reserved = [a for a in engine_args if a in RESERVED_ENGINE_FLAGS]
    if reserved:
        raise SystemExit(f"[llm-dock] {', '.join(reserved)} is set by the launcher, not a param")

    pack = Path(args.pack)
    family = FAMILIES[pack_family(pack)]
    gpus = [int(g) for g in str(args.gpu).split(",") if g.strip()]

    cfg = {
        "exe": str(maya_root / family["exe"]),
        "args": [family["pack_flag"], str(pack), *engine_args],
        "cwd": str(maya_root),
        "tokenizer": str(pack / "tokenizer"),
        "model_name": args.model_name,
        "gpu": gpus,
        "sampling": {
            "temperature": args.sampling_temperature,
            "top_p": args.sampling_top_p if args.sampling_top_p is not None else family["top_p"],
        },
        "reasoning_effort": _effort(args.reasoning_effort),
        "lib_dirs": [],
        "host": "0.0.0.0",
        "port": args.port,
        "engine_ready_s": args.engine_ready_s,
        "log": str(state_dir / "engine.log"),
        "env": {},
    }
    if args.thinking_budget is not None:
        cfg["thinking_budget"] = args.thinking_budget
    if args.idle_unload is not None:
        cfg["idle_unload_s"] = args.idle_unload
    return cfg, args.api_key


def server_argv(config_path: Path, port: int, maya_root: Path = MAYA_ROOT) -> List[str]:
    return [sys.executable, str(maya_root / "serve" / "server.py"), "--engine", "strata",
            "--config", str(config_path), "--host", "0.0.0.0", "--port", str(port)]


def main(argv: List[str]) -> None:
    cfg, api_key = build_config(argv)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    config_path = STATE_DIR / "maya.json"
    tmp = config_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    os.replace(tmp, config_path)

    # server.py sends the engine's stderr only to cfg["log"] (DEVNULL without
    # one), so the log is tailed onto stdout for `docker logs`. STRATA_SERVER_LOG=0
    # keeps the server's own lines out of that file, or they would print twice.
    log = Path(cfg["log"])
    log.write_text("", encoding="utf-8")
    subprocess.Popen(["tail", "-n", "+1", "-F", str(log)], stderr=subprocess.DEVNULL)

    env = dict(os.environ, STRATA_SERVER_LOG="0", MAYA_UPDATE_CHECK="0", PYTHONUNBUFFERED="1",
               STRATA_API_KEY=api_key)
    print(f"[llm-dock] {cfg['exe']} {' '.join(cfg['args'])}", flush=True)
    argv_out = server_argv(config_path, cfg["port"])
    os.execve(argv_out[0], argv_out, env)


if __name__ == "__main__":
    main(sys.argv[1:])
