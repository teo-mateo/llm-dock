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


def find_text_bounds(xml, label):
    root = ET.fromstring(xml)
    fallback = None
    for node in root.iter("node"):
        if node.get("text") != label:
            continue
        match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.get("bounds", ""))
        if not match:
            continue
        bounds = tuple(map(int, match.groups()))
        if node.get("clickable") == "true":
            return bounds
        if fallback is None:
            fallback = bounds
    return fallback


def find_tags(xml, needle=""):
    root = ET.fromstring(xml)
    tags = set()
    for node in root.iter("node"):
        resource = node.get("resource-id", "")
        if not resource:
            continue
        tag = resource.rsplit(":id/", 1)[-1]
        if needle in tag:
            tags.add(tag)
    return sorted(tags)


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
    parser.add_argument("action", choices=["wait", "tap", "bounds", "absent", "tags", "tap-text", "absent-text"])
    parser.add_argument("tag", nargs="?", default="", help="exact tag, exact label for *-text, or a substring filter for tags")
    args = parser.parse_args()
    if not args.device.startswith("emulator-"):
        parser.error("only emulator targets are permitted")
    if not 0 < args.timeout <= 120:
        parser.error("timeout must be in (0, 120]")
    if args.action not in ("tags",) and not args.tag:
        parser.error(f"{args.action} needs a {'label' if args.action.endswith('-text') else 'tag'}")
    sdk = Path(os.environ.get("ANDROID_SDK_ROOT", os.environ.get("ANDROID_HOME", str(Path.home() / "Android/Sdk"))))
    adb = str(sdk / "platform-tools/adb")
    command = [adb, "-s", args.device]
    deadline = time.monotonic() + (args.timeout if args.action != "tags" else 10)
    while True:
        remaining = max(0.1, deadline - time.monotonic())
        try:
            result = subprocess.run(command + ["exec-out", "uiautomator", "dump", "/dev/tty"],
                                    capture_output=True, text=True, check=True, timeout=min(5, remaining))
        except subprocess.TimeoutExpired:
            if time.monotonic() >= deadline:
                raise ValueError(f"UI dump timed out waiting for tag: {args.tag}") from None
            continue
        try:
            xml = hierarchy(result.stdout)
        except ValueError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.3)
            continue
        if args.action == "tags":
            for tag in find_tags(xml, args.tag):
                print(tag)
            return
        if args.action in ("tap-text", "absent-text"):
            bounds = find_text_bounds(xml, args.tag)
            if args.action == "absent-text":
                if bounds is not None:
                    raise ValueError(f"label unexpectedly present: {args.tag}")
                print(f"absent-text: {args.tag}")
                return
            if bounds is not None:
                x1, y1, x2, y2 = bounds
                subprocess.run(command + ["shell", "input", "tap", str((x1 + x2) // 2), str((y1 + y2) // 2)],
                               check=True, capture_output=True, timeout=10)
                print(f"tap-text: {args.tag} {bounds}")
                return
            if time.monotonic() >= deadline:
                raise ValueError(f"label not found: {args.tag}")
            time.sleep(min(0.3, max(0, deadline - time.monotonic())))
            continue
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
            ids = find_tags(xml)
            raise ValueError(f"tag not found: {args.tag}; resource IDs: {', '.join(ids)}")
        time.sleep(min(0.3, max(0, deadline - time.monotonic())))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, ET.ParseError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(f"UI check failed: {type(error).__name__}: {error}")
