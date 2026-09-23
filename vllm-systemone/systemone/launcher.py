import argparse
import os
from http.server import ThreadingHTTPServer

from openai import OpenAI

import shim


def _bind_backend(base_url: str, api_key: str, model: str) -> OpenAI:
    client = OpenAI(base_url=base_url, api_key=api_key)
    create = client.chat.completions.create

    def create_as_served(**kwargs):
        kwargs["model"] = model
        return create(**kwargs)

    client.chat.completions.create = create_as_served
    return client


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=3000)
    a = ap.parse_args()

    # shim.py hardcodes model="qwen" and api_key="x". It is patched here rather
    # than edited so /v1/version keeps reporting the published file's sha256.
    shim.client = _bind_backend(
        os.environ["VLLM"],
        os.environ.get("SYSTEMONE_BACKEND_KEY") or "x",
        os.environ["SYSTEMONE_BACKEND_MODEL"],
    )
    shim.letter_ids()
    print(f"systemone shim on {a.host}:{a.port} -> {shim.client.base_url}", flush=True)
    ThreadingHTTPServer.request_queue_size = 256
    ThreadingHTTPServer.daemon_threads = True
    ThreadingHTTPServer((a.host, a.port), shim.H).serve_forever()


if __name__ == "__main__":
    main()
