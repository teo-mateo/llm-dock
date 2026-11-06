#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import subprocess
from urllib.request import urlopen

from scenarios import NAMES


def prepare(device, port, adb):
    if not device.startswith("emulator-"):
        raise ValueError("only emulator targets are permitted")
    if not 0 < port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    with urlopen(f"http://127.0.0.1:{port}/__fixture/scenario", timeout=5) as response:
        state = json.load(response)
    if not isinstance(state, dict) or state.get("scenario") not in NAMES:
        raise ValueError("port does not serve the expected Android Pi fixture")
    command = [str(adb), "-s", device]

    def run(*args):
        return subprocess.run(command + list(args), capture_output=True, text=True,
                              check=True, timeout=10).stdout.strip()

    if run("get-state") != "device":
        raise ValueError("emulator is not connected and authorized")
    local = f"tcp:{port}"
    mappings = [line.split()[-2:] for line in run("reverse", "--list").splitlines()]
    existing = [pair for pair in mappings if len(pair) == 2 and pair[0] == local]
    if any(pair[1] != local for pair in existing):
        raise ValueError(f"{local} already forwards elsewhere; do not overwrite another mapping")
    created = not existing
    if created:
        run("reverse", local, local)
    verified = [line.split()[-2:] for line in run("reverse", "--list").splitlines()]
    if [local, local] not in verified:
        raise ValueError("adb did not confirm the reverse mapping; inspect reverse --list")
    return {"url": f"http://127.0.0.1:{port}", "scenario": state["scenario"],
            "mapping_created": created, "device": device}


def main():
    parser = argparse.ArgumentParser(description="Verify fixture readiness and emulator forwarding")
    parser.add_argument("--device", required=True)
    parser.add_argument("--port", type=int, default=3999)
    parser.add_argument("--reserved", action="store_true",
                        help="confirm you hold the emulator reservation")
    args = parser.parse_args()
    if not args.reserved:
        parser.error("reserve the emulator with the PO first, then pass --reserved")
    sdk = Path(os.environ.get("ANDROID_SDK_ROOT", os.environ.get("ANDROID_HOME", str(Path.home() / "Android/Sdk"))))
    result = prepare(args.device, args.port, sdk / "platform-tools/adb")
    print(json.dumps(result))
    print("Fixture ready: connect the emulator app to that URL with dummy password 'fixture'.")
    print("Restore the previous app connection after testing. Remove only mappings you created.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(f"Fixture setup failed: {error}")
