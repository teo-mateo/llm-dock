#!/usr/bin/env python3
import argparse
import json
from urllib.error import URLError
from urllib.request import Request, urlopen

from scenarios import NAMES


def main():
    parser = argparse.ArgumentParser(description="Change the local Android fixture without sleeps")
    parser.add_argument("name", choices=NAMES)
    parser.add_argument("--port", type=int, default=3999)
    args = parser.parse_args()
    if not 0 < args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    request = Request(
        f"http://127.0.0.1:{args.port}/__fixture/scenario",
        data=json.dumps({"name": args.name}).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urlopen(request, timeout=5) as response:
        print(response.read().decode())


if __name__ == "__main__":
    try:
        main()
    except (URLError, OSError) as error:
        raise SystemExit(f"Fixture not available: {error}")
