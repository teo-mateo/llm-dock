#!/usr/bin/env python3
import argparse
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import Request, urlopen

from transcript import INSTANCE_ID, SESSION_ID

UI = Path(__file__).resolve().parents[2] / "android-emulator/scripts/ui.py"
BASE = "http://127.0.0.1:3999"


def fixture(body=None):
    request = Request(BASE + "/__fixture/transcript", data=None if body is None else json.dumps(body).encode(),
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def ui(device, *arguments):
    subprocess.run([sys.executable, str(UI), "--device", device, "--timeout", "90", *arguments],
                   check=True, timeout=105)


def checkpoint(device, expected_cursor):
    sdk = Path(os.environ.get("ANDROID_SDK_ROOT", str(Path.home() / "Android/Sdk")))
    command = [str(sdk / "platform-tools/adb"), "-s", device, "exec-out", "run-as", "com.hpz.llmdockchat"]
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        listing = subprocess.run(command + ["find", "cache/pi-sessions", "-name", "*.json.gz"],
                                 capture_output=True, check=True, timeout=10).stdout.decode().splitlines()
        if len(listing) > 1:
            raise ValueError("Expected isolated fixture Pi cache; preserve original data before testing")
        if listing:
            compressed = subprocess.run(command + ["cat", listing[0]], capture_output=True, check=True, timeout=10).stdout
            raw = gzip.decompress(compressed)
            data = json.loads(raw)
            identity = data["identity"]
            if identity != {"server": BASE, "key": {"sessionId": SESSION_ID, "instanceId": INSTANCE_ID}}:
                raise ValueError("Unexpected cache namespace; no content printed")
            if data["lastSeq"] == expected_cursor:
                items = data["checkpoint"]["items"]
                markers = {}
                tools = [item for item in items if item["type"] == "tool"]
                for item in items:
                    if item["type"] != "assistant":
                        continue
                    first_line = item["text"].split("\n", 1)[0]
                    if first_line.startswith(("CACHE_BASELINE_END_", "CACHE_SUFFIX_")):
                        markers[first_line] = markers.get(first_line, 0) + 1
                if len({item["id"] for item in items}) != len(items) or any(count != 1 for count in markers.values()):
                    raise ValueError("Duplicated fixture items/markers")
                if len({item["callId"] for item in tools}) != len(tools):
                    raise ValueError("Duplicated fixture tool calls")
                return {"cursor": data["lastSeq"], "items": len(items), "tools": len(tools),
                        "compressed_bytes": len(compressed), "json_bytes": len(raw), "markers": markers}
        time.sleep(0.1)
    raise ValueError("Expected committed checkpoint cursor was not observed within 30 seconds")


def main():
    parser = argparse.ArgumentParser(description="Observe real emulator Pi UI/cache using the shared fixture")
    parser.add_argument("case", choices=["miss", "hit"])
    parser.add_argument("--device", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.device.startswith("emulator-"):
        parser.error("reserved emulator only")
    initial = fixture()
    fixture({"action": "gate", "gate": "open" if args.case == "miss" else "replay"})
    started = time.monotonic()
    ui(args.device, "tap", f"pi_session_{SESSION_ID}_{INSTANCE_ID}")
    ui(args.device, "wait", "pi_assistant_text")
    first_content = time.monotonic()
    if args.case == "hit":
        ui(args.device, "wait-text", "Cached · checking…")
        waiting = fixture()["requests"][-1]
        if waiting["after"] <= 0 or waiting["sent_events"] != 0 or waiting["summary_sent"]:
            raise ValueError("Cache-hit content was not isolated from replay")
        if waiting["after"] < initial["latest_seq"]:
            fixture({"action": "gate", "gate": "summary"})
            ui(args.device, "wait-text", "Catching up…")
    released = time.monotonic()
    if args.case == "hit":
        fixture({"action": "gate", "gate": "open"})
    ui(args.device, "wait-text", "Connected")
    connected = time.monotonic()
    stats = fixture()
    request = stats["requests"][-1]
    expected_count = stats["latest_seq"] - request["after"]
    if request["sent_events"] != expected_count or not request["summary_sent"]:
        raise ValueError("Replay counters disagree with accepted cursor")
    if args.case == "miss" and request["after"] != 0:
        raise ValueError("Expected a cache miss, not a restored cursor")
    committed = checkpoint(args.device, stats["latest_seq"])
    if committed["items"] != stats["event_count"] // 16 * 7:
        raise ValueError("Unexpected fixture transcript cardinality")
    result = {
        "case": args.case, "device": args.device,
        "method": "host monotonic tap-command start to UIAutomator-observed assistant/current labels; includes tag lookup, adb and dump overhead",
        "tap_command_to_first_assistant_ms": round((first_content - started) * 1000),
        "tap_command_to_connected_ms": round((connected - started) * 1000),
        "summary_release_to_connected_ms": round((connected - released) * 1000) if args.case == "hit" else None,
        "gate_controlled": args.case == "hit", "initial_event_count": initial["event_count"],
        "event_json_bytes": stats["event_json_bytes"], "request": request, "checkpoint": committed,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("case", "tap_command_to_first_assistant_ms", "tap_command_to_connected_ms")}))


if __name__ == "__main__":
    main()
