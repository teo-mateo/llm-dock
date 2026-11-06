#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET


def find_bounds(xml, tag):
    root = ET.fromstring(xml)
    for node in root.iter("node"):
        resource = node.get("resource-id", "")
        if resource != tag and resource.rsplit(":id/", 1)[-1] != tag:
            continue
        match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.get("bounds", ""))
        if match:
            return tuple(map(int, match.groups()))
    return None


def hierarchy(raw):
    start = raw.find("<?xml")
    if start < 0:
        start = raw.find("<hierarchy")
    end = raw.rfind("</hierarchy>")
    if start < 0 or end < 0:
        raise ValueError("device returned no UI hierarchy")
    return raw[start:end + len("</hierarchy>")]


def main():
    parser = argparse.ArgumentParser(description="Find/tap exact Compose tags on a reserved emulator")
    parser.add_argument("--device", required=True)
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("action", choices=["wait", "tap", "bounds", "absent"])
    parser.add_argument("tag")
    args = parser.parse_args()
    if not args.device.startswith("emulator-"):
        parser.error("only emulator targets are permitted")
    if not 0 < args.timeout <= 120:
        parser.error("timeout must be in (0, 120]")
    sdk = Path(os.environ.get("ANDROID_SDK_ROOT", os.environ.get("ANDROID_HOME", str(Path.home() / "Android/Sdk"))))
    adb = str(sdk / "platform-tools/adb")
    command = [adb, "-s", args.device]
    deadline = time.monotonic() + args.timeout
    while True:
        remaining = max(0.1, deadline - time.monotonic())
        result = subprocess.run(command + ["exec-out", "uiautomator", "dump", "/dev/tty"],
                                capture_output=True, text=True, check=True, timeout=remaining)
        xml = hierarchy(result.stdout)
        bounds = find_bounds(xml, args.tag)
        if args.action == "absent":
            if bounds is not None:
                raise ValueError(f"tag unexpectedly present: {args.tag}")
            print(f"absent: {args.tag}")
            return
        if bounds is not None:
            x1, y1, x2, y2 = bounds
            if x2 <= x1 or y2 <= y1:
                raise ValueError(f"tag has empty bounds: {args.tag}")
            if args.action == "tap":
                subprocess.run(command + ["shell", "input", "tap", str((x1 + x2) // 2), str((y1 + y2) // 2)],
                               check=True, capture_output=True, timeout=10)
            print(f"{args.action}: {args.tag} {bounds}")
            return
        if time.monotonic() >= deadline:
            ids = sorted({node.get("resource-id", "") for node in ET.fromstring(xml).iter("node")})
            raise ValueError(f"tag not found: {args.tag}; resource IDs: {', '.join(filter(None, ids))}")
        time.sleep(min(0.3, max(0, deadline - time.monotonic())))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, ET.ParseError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(f"UI check failed: {type(error).__name__}: {error}")
