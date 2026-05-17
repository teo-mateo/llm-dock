#!/usr/bin/env python3
"""Sanity check: with the new default prompt, can the model still answer
a normal non-tool question without falling on its face?"""
import json
import os
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "dashboard"))

from chat.constants import DEFAULT_MAIN_SYSTEM_PROMPT  # noqa: E402

API_KEY = os.environ.get("LLM_DOCK_API_KEY")
if not API_KEY:
    sys.exit("LLM_DOCK_API_KEY env var is required (the model-service API key from services.json)")

body = {
    "model": "vllm-qwen3-6-27b-bf16",
    "messages": [
        {"role": "system", "content": DEFAULT_MAIN_SYSTEM_PROMPT},
        {"role": "user", "content": "Explain Python's GIL in 3 sentences."},
    ],
    "temperature": 0.2,
    "max_tokens": 2048,
}
r = requests.post(
    "http://localhost:3307/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    },
    json=body,
    timeout=180,
)
data = r.json()
msg = data["choices"][0]["message"]
print("finish_reason:", data["choices"][0].get("finish_reason"))
print("content_len:", len(msg.get("content") or ""))
print()
print(msg.get("content") or "(empty)")
