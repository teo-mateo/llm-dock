#!/opt/pennyroyal/.venv/bin/python
"""Keep Pennyroyal's recipes intact while supplying LLM-Dock's identity/auth.

Installed both as the container entrypoint and as the recipe's sglang executable.
Sizing and checkpoint quantization are resolved before cache derivation. Only
identity/auth flags are appended after that derivation.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

REPO_ROOT = "/opt/pennyroyal"
MANAGED_ARGS_ENV = "LLM_DOCK_SGLANG_MANAGED_ARGS"
COMPAT_DIR = "/usr/local/cuda-13.0/compat"


def configure_cuda_compat(env):
    """Select container-only user-mode libraries; never modify the host driver."""
    mode = env.get("SGLANG_USE_CUDA_COMPAT", "auto")
    if mode not in ("auto", "0", "1"):
        raise ValueError("SGLANG_USE_CUDA_COMPAT must be auto, 0, or 1")
    if mode == "0":
        return
    if mode == "auto":
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                capture_output=True, text=True, check=True, timeout=5,
            )
            # CUDA 13.0 Torch wheels require R580. Newer drivers use their own
            # libraries rather than the older compatibility package.
            if int(result.stdout.split(".", 1)[0]) >= 580:
                return
        except (OSError, ValueError, subprocess.SubprocessError):
            return
    if not (Path(COMPAT_DIR) / "libcuda.so.1").is_file():
        raise RuntimeError(f"CUDA compatibility libraries missing from {COMPAT_DIR}")
    env["LD_LIBRARY_PATH"] = COMPAT_DIR + (
        ":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else ""
    )


def recipe_command(argv, env):
    """Turn a recipe's argv into the real server command without shell parsing."""
    managed = json.loads(env[MANAGED_ARGS_ENV])
    return [f"{REPO_ROOT}/.venv/bin/sglang-runtime", *argv, *managed]


def profile_command(argv, env):
    parser = argparse.ArgumentParser(description="LLM-Dock Pennyroyal launcher")
    parser.add_argument("--profile", choices=("next", "next-plain", "27b"), default="next")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--served-model-name", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--draft-model-path")
    args = parser.parse_args(argv)
    if args.profile == "27b" and not (args.draft_model_path or env.get("DRAFT_MODEL")):
        parser.error("27b requires --draft-model-path (the DFlash2 checkpoint directory)")
    env["TARGET_MODEL"] = args.model_path
    if args.profile in ("next", "next-plain"):
        checkpoint = json.loads((Path(args.model_path) / "config.json").read_text())
        method = checkpoint.get("quantization_config", {}).get("quant_method")
        if method == "compressed-tensors":
            env["LLM_DOCK_TARGET_QUANTIZATION"] = method
        elif method in ("modelopt", "modelopt_fp4"):
            env["LLM_DOCK_TARGET_QUANTIZATION"] = "modelopt_fp4"
        else:
            parser.error(f"Flash-Next requires ModelOpt NVFP4 or compressed-tensors; got {method!r}")
        for name in ("PENNY_CONTEXT_LENGTH", "PENNY_PREFILL_CHUNK_SIZE",
                     "MAX_RUNNING_REQUESTS", "MAX_MAMBA_CACHE_SIZE", "PENNY_HICACHE_SIZE_GB"):
            if name in env and (not env[name].isdigit() or int(env[name]) < 1):
                parser.error(f"{name} must be a positive integer")
        if "PENNY_CONTEXT_LENGTH" in env and int(env["PENNY_CONTEXT_LENGTH"]) > 524288:
            parser.error("PENNY_CONTEXT_LENGTH cannot exceed the recipe's 524288-token limit")
        if "PENNY_MEM_FRACTION_STATIC" in env:
            try:
                fraction = float(env["PENNY_MEM_FRACTION_STATIC"])
            except ValueError:
                fraction = 0
            if not 0 < fraction < 1:
                parser.error("PENNY_MEM_FRACTION_STATIC must be between 0 and 1")
    if args.draft_model_path:
        env["DRAFT_MODEL"] = args.draft_model_path
    env[MANAGED_ARGS_ENV] = json.dumps([
        "--host", "0.0.0.0", "--port", "8001",
        "--served-model-name", args.served_model_name, "--api-key", args.api_key,
    ])
    if args.profile in ("next", "next-plain"):
        recipe = "serve-flash-next-frspec.sh" if args.profile == "next" else "serve-flash-next.sh"
        return ["/usr/local/bin/pennyroyal", "exec", "bash",
                f"{REPO_ROOT}/configs/pennyroyal/llm-dock-{recipe}"]
    return ["/usr/local/bin/pennyroyal", args.profile]


def main():
    argv = sys.argv[1:]
    env = os.environ.copy()
    # The upstream recipe execs `sglang serve ...`; the container entrypoint
    # receives only managed identity and profile flags.
    if argv and argv[0] == "serve":
        command = recipe_command(argv, env)
    else:
        command = profile_command(argv, env)
        configure_cuda_compat(env)
    os.execve(command[0], command, env)


if __name__ == "__main__":
    main()
