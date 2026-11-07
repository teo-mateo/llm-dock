#!/usr/bin/env python3
import argparse
import json
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description="Control the loopback Pi transcript fixture")
    parser.add_argument("action", choices=["stats", "reset", "append", "gate", "offline", "online", "end", "remove"])
    parser.add_argument("--gate", choices=["open", "replay", "summary"])
    parser.add_argument("--port", type=int, default=3999)
    args = parser.parse_args()
    if not 0 < args.port <= 65535 or (args.action == "gate" and args.gate is None):
        parser.error("valid port and --gate for gate action are required")
    url = f"http://127.0.0.1:{args.port}/__fixture/transcript"
    request = Request(url)
    if args.action != "stats":
        request = Request(url, data=json.dumps({"action": args.action, "gate": args.gate}).encode(),
                          headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=10) as response:
        print(json.dumps(json.load(response), indent=2))


if __name__ == "__main__":
    main()
