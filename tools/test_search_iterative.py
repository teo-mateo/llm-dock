#!/usr/bin/env python3
"""
Reproducible test harness for studying how the chat model handles a
multi-step web research request.

Drives `vllm-qwen3-6-27b-bf16` (or any OpenAI-compatible service) directly,
fakes the MCP tool results so the loop is deterministic + fast, and captures
the full sequence: every round's tool calls, reasoning content, finish
reason, elapsed time, and token usage. Output is a JSON trace plus a short
human summary.

Run:
  python tools/test_search_iterative.py
  python tools/test_search_iterative.py --no-parallel-tool-calls
  python tools/test_search_iterative.py --system-prompt tools/prompts/focused.txt

The script does NOT touch the dashboard or the live MCP servers — it speaks
to vLLM directly and synthesizes tool results in-process.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "dashboard"))

DEFAULT_SERVICE_URL = "http://localhost:3307/v1/chat/completions"
DEFAULT_API_KEY = "llmd-cfc6b6ef75620adc289764238a831f10cb21"
DEFAULT_MODEL = "vllm-qwen3-6-27b-bf16"

USER_PROMPT = (
    "I need to replace the thermal pads in my rtx 3090. what should I buy "
    "from Amazon? I am in belgium; it's a DELL OEM card. I need to replace "
    "the thermal pads on the back of it, not the actual GPU processor. "
    "please use web search and web fetch; suggest best product to buy from "
    "Amazon."
)

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web. Returns up to n_results items, each with "
                "title, url, snippet."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query string."},
                    "n_results": {"type": "integer", "default": 5, "minimum": 1, "maximum": 10},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_readable",
            "description": (
                "Fetch a single URL and return its main text content as "
                "markdown. Use a URL copied verbatim from a web_search result."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Absolute URL to fetch."},
                },
                "required": ["url"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Fake tool results — small, deterministic, but content-rich enough that the
# model has signal to refine.
# ---------------------------------------------------------------------------

# Canned results live as a flat catalog; the fake search picks the best
# matches per query so the model sees DIFFERENT results when it refines
# (vs. the placeholder-looking same-results-every-time loop in v1).
CATALOG = [
    {
        "id": "dell-community",
        "topics": ["dell", "oem", "rtx 3090", "aurora", "alienware", "thermal pad", "backplate", "thickness"],
        "title": "Dell OEM RTX 3090 (Alienware Aurora R11) — replacing thermal pads on backplate",
        "url": "https://www.dell.com/community/en/conversations/alienware-desktops/dell-oem-rtx-3070-3080-3090-thermal-pad-thickness/647fa31bf4ccf8a8de8da85d",
        "snippet": (
            "Dell OEM RTX 3070/3080/3090 thermal pad thickness and "
            "conductivity. Thread confirms the Dell OEM 3090 (Aurora R11) "
            "uses 2.0mm pads on the backplate side over the VRAM chips and "
            "1.5mm on the front; same as FE."
        ),
    },
    {
        "id": "schematic-expert",
        "topics": ["rtx 3090", "thermal pad", "thickness", "size", "vram", "vrm", "backplate", "schematic"],
        "title": "RTX 3080/Ti, RTX 3090/Ti — Thermal Pad Sizes (Schematic-Expert)",
        "url": "https://www.schematic-expert.com/nvidia/nvidia-rtx-3080-ti-3090-ti/rtx-3080-ti-rtx3090-ti-thermal-pad-sizes/",
        "snippet": (
            "Full pad map for RTX 3080/3080 Ti/3090/3090 Ti. Back: 2.0mm "
            "memory pads (3 strips of 80x40x1). Front: 1.5mm. Recommended "
            "material 12 W/mK or better."
        ),
    },
    {
        "id": "tomshardware",
        "topics": ["rtx 3090", "thermal pad", "gddr6x", "replace", "improvement"],
        "title": "Replacing GeForce RTX 3090 Thermal Pads Improves GDDR6X Temps by 25C | Tom's Hardware",
        "url": "https://www.tomshardware.com/news/replacing-geforce-rtx-3090-thermal-pads-improves-temps-by-25c",
        "snippet": (
            "Repad guide drops GDDR6X temps by ~25C. Used Thermalright "
            "Odyssey 1.5mm front / 2.0mm back. Recommends 12.8 W/mK pads."
        ),
    },
    {
        "id": "amazon-de-odyssey-2mm-85x45",
        "topics": ["thermalright", "odyssey", "2mm", "amazon", "amazon.de", "belgium", "85x45"],
        "title": "Thermalright Odyssey Thermal Pad 12.8 W/mK 85x45x2.0mm — amazon.de",
        "url": "https://www.amazon.de/-/en/Thermalright-Conductivity-Performance-Resistance-Insulating/dp/B09KKQ7TPN",
        "snippet": (
            "Thermalright Odyssey Thermal Pad 85x45x2.0mm, 12.8 W/mK, single "
            "sheet. Heat resistance to 200°C. Ships to Belgium. €11.90."
        ),
    },
    {
        "id": "amazon-de-odyssey-2mm-120x120",
        "topics": ["thermalright", "odyssey", "2mm", "amazon", "amazon.de", "belgium", "120x120", "large"],
        "title": "Thermalright Odyssey Thermal Pad 120x120x2.0mm 12.8 W/mK — amazon.de",
        "url": "https://www.amazon.de/-/en/Thermalright-Conductivity-Performance-Resistance-Insulating/dp/B0C8R1HQ5G",
        "snippet": (
            "Thermalright Odyssey Thermal Pad 120x120x2.0mm, 12.8 W/mK, "
            "single sheet, easy to cut. Ships from Germany to Belgium. €18.99."
        ),
    },
    {
        "id": "amazon-de-arctic-tp3",
        "topics": ["arctic", "tp-3", "2mm", "amazon", "amazon.de", "belgium", "alternative"],
        "title": "ARCTIC TP-3 Thermal Pad 100x100x2.0mm, 4 W/mK — amazon.de",
        "url": "https://www.amazon.de/ARCTIC-TP-3-Thermal-Performance-Heatsink/dp/B09M4G3X8Y",
        "snippet": (
            "ARCTIC TP-3 100x100x2.0mm. 4 W/mK. Budget alternative. €7.99. "
            "Ships to Belgium."
        ),
    },
    {
        "id": "reddit-repad",
        "topics": ["reddit", "rtx 3090", "repad", "thermal pad", "experience"],
        "title": "RTX 3090 repad results — r/buildapc",
        "url": "https://www.reddit.com/r/buildapc/comments/1d8k9r2/rtx_3090_repad_thermalright_odyssey_results/",
        "snippet": (
            "Hot-take thread on RTX 3090 GDDR6X temps post-repad. Most users "
            "land on Thermalright Odyssey 12.8 W/mK; Gelid GP-Extreme is "
            "discouraged for high-power GPUs."
        ),
    },
    {
        "id": "linus-tech-tips",
        "topics": ["rtx 3090", "vram", "cooling", "alienware", "r11", "r12", "diy"],
        "title": "3090 VRAM cooling project for Alienware R11/R12 — Linus Tech Tips",
        "url": "https://linustechtips.com/topic/1318518-3090-vram-cooling-project-for-alienware-r11r12-will-probably-work-with-any-card-if-you-have-space/",
        "snippet": (
            "Project log of Dell OEM 3090 VRAM cooling improvements in an "
            "Alienware R11. Confirms 2.0mm backplate pads, 1.5mm front."
        ),
    },
]


def _score(item, query_terms):
    return sum(1 for t in query_terms if t in item["topics"] or t in item["title"].lower() or t in item["snippet"].lower())


def fake_web_search(args):
    query = ((args or {}).get("query") or "").lower()
    n = int((args or {}).get("n_results", 5))
    terms = [t.strip(' "\'.,()[]') for t in query.split() if len(t) > 2]
    scored = sorted(((_score(item, terms), item) for item in CATALOG), key=lambda p: -p[0])
    results = []
    for score, item in scored:
        if score == 0:
            continue
        results.append({"title": item["title"], "url": item["url"], "snippet": item["snippet"]})
        if len(results) >= n:
            break
    if not results:
        # Tail fallback so the model sees *something* on a wildly off-target query
        results = [{"title": item["title"], "url": item["url"], "snippet": item["snippet"]} for _, item in scored[:min(n, 3)]]
    return json.dumps({"query": args.get("query"), "results": results})


CANNED_FETCH = {
    "dell.com": (
        "# Dell Community — Dell OEM RTX 3070/3080/3090 thermal pad "
        "thickness and conductivity\n\n"
        "Thread author asked about replacing thermal pads on a Dell OEM "
        "RTX 3090 from an Alienware Aurora R11. Replies confirm:\n\n"
        "- Front side (between GPU die / VRAM and main heatsink): **1.5mm**\n"
        "- Back side (between PCB rear and metal backplate, over the GDDR6X chips): **2.0mm**\n\n"
        "Recommended material: ≥12 W/mK. Thermalright Odyssey 12.8 W/mK is the most common pick. "
        "Avoid pads softer than 70 Shore-OO for high-clamp-force backplates."
    ),
    "schematic-expert.com": (
        "# RTX 3080/Ti and RTX 3090/Ti — Thermal pad sizes\n\n"
        "Reference card and Dell OEM share the same memory layout.\n\n"
        "## Back side\n- VRAM (GDDR6X): **2.0mm**, 3 strips of 80x40\n\n"
        "## Front side\n- VRAM: 1.5mm\n- VRM: 1.5mm\n\n"
        "Thermalright Odyssey 12.8 W/mK is widely used. Sheet sizes 85x45 or 120x120 cover the entire backplate area with one cut."
    ),
    "tomshardware.com": (
        "# Replacing GeForce RTX 3090 Thermal Pads Improves GDDR6X Temps By 25C\n\n"
        "Used: Thermalright Odyssey 12.8 W/mK, 1.5mm front + 2.0mm back. "
        "Result: GDDR6X memory junction temps dropped ~25C under sustained load. "
        "Cleaning with isopropyl is recommended; new pads should be cut to size, not stretched."
    ),
    "amazon.de": (
        "## Thermalright Odyssey Thermal Pad — amazon.de\n\n"
        "Variants in stock, shipping to Belgium:\n"
        "- 85x45x2.0mm — €11.90 — ASIN B09KKQ7TPN — 12.8 W/mK\n"
        "- 120x120x2.0mm — €18.99 — ASIN B0C8R1HQ5G — 12.8 W/mK\n"
        "- 100x100x1.5mm — €13.50 — 12.8 W/mK\n\n"
        "Reviews specifically mention RTX 3080/3090 backplate use; reviewers report 20-25C GDDR6X temp drop."
    ),
    "reddit.com": (
        "# RTX 3090 repad — community consensus\n\n"
        "- Top pick: Thermalright Odyssey 12.8 W/mK (back 2.0mm, front 1.5mm).\n"
        "- Budget: Arctic TP-3 (4 W/mK) — works but smaller temp delta.\n"
        "- Avoid Gelid GP-Extreme on high-power 3090 (compression / pump-out issues)."
    ),
    "linustechtips.com": (
        "# 3090 VRAM cooling project for Alienware R11/R12 — OP report\n\n"
        "Dell OEM RTX 3090 inside an Alienware Aurora R11. Repad with "
        "Thermalright Odyssey 2.0mm on the backplate side, 1.5mm front. "
        "Memory hotspot dropped from 102C to 78C under load."
    ),
}


FAILED_URLS = {
    # 403 to exercise the "don't retry" path
    "https://www.reddit.com/r/buildapc/comments/1d8k9r2/rtx_3090_repad_thermalright_odyssey_results/": (
        403,
        "Forbidden (Cloudflare)",
    ),
}


def fake_fetch_readable(args):
    url = (args or {}).get("url", "")
    if url in FAILED_URLS:
        status, msg = FAILED_URLS[url]
        return json.dumps({"ok": False, "url": url, "status": status, "error": msg})
    for domain, body in CANNED_FETCH.items():
        if domain in url:
            return json.dumps({"ok": True, "url": url, "content": body, "status": 200})
    return json.dumps({"ok": False, "url": url, "status": 404, "error": "Not found"})


def fake_tool(name, args):
    if name == "web_search":
        return fake_web_search(args)
    if name == "fetch_readable":
        return fake_fetch_readable(args)
    return json.dumps({"error": f"unknown tool: {name}"})


# ---------------------------------------------------------------------------
# Loop driver
# ---------------------------------------------------------------------------


def load_system_prompt(path_or_keyword):
    """Resolve the system prompt source.

    - 'default' (or unset): import DEFAULT_MAIN_SYSTEM_PROMPT from the
      dashboard module so the harness mirrors a fresh conversation's
      starting state — and append the same date line `_stream_response`
      injects at request time.
    - any other value: treat as a path to a text file. No date injection;
      put a date in your prompt file yourself if you need it.
    """
    if path_or_keyword in (None, "", "default"):
        import datetime
        from chat.constants import DEFAULT_MAIN_SYSTEM_PROMPT
        today = datetime.date.today()
        date_line = (
            f"Current date: {today.isoformat()} ({today.strftime('%A')}). "
            "Use this as \"today\" when interpreting time-sensitive questions."
        )
        return f"{DEFAULT_MAIN_SYSTEM_PROMPT}\n\n{date_line}"
    return Path(path_or_keyword).read_text()


def run(
    url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_rounds: int,
    parallel_tool_calls: bool,
    temperature: float,
    output_path: str,
):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    trace = {
        "service_url": url,
        "model": model,
        "parallel_tool_calls": parallel_tool_calls,
        "temperature": temperature,
        "max_rounds": max_rounds,
        "system_prompt_chars": len(system_prompt),
        "user_prompt": user_prompt,
        "rounds": [],
    }

    for round_i in range(1, max_rounds + 1):
        round_start = time.time()
        body = {
            "model": model,
            "messages": messages,
            "tools": TOOLS_SCHEMA,
            "tool_choice": "auto",
            "parallel_tool_calls": parallel_tool_calls,
            "temperature": temperature,
            "max_tokens": 8192,
        }
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
            timeout=600,
        )
        if r.status_code != 200:
            trace["error"] = f"HTTP {r.status_code}: {r.text[:500]}"
            break
        data = r.json()
        choice = data["choices"][0]
        msg = choice["message"]
        finish = choice.get("finish_reason")

        round_log = {
            "round": round_i,
            "elapsed_s": round(time.time() - round_start, 2),
            "finish_reason": finish,
            "content": msg.get("content"),
            "reasoning": msg.get("reasoning_content") or msg.get("reasoning"),
            "tool_calls": msg.get("tool_calls") or [],
            "usage": data.get("usage"),
        }
        trace["rounds"].append(round_log)

        tool_calls = msg.get("tool_calls") or []
        if finish != "tool_calls" or not tool_calls:
            messages.append({"role": "assistant", "content": msg.get("content")})
            break

        # Echo assistant message with tool_calls to keep the API happy
        messages.append({
            "role": "assistant",
            "content": msg.get("content") or "",
            "tool_calls": tool_calls,
        })
        # Execute every tool call the model requested (faked)
        for tc in tool_calls:
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            result = fake_tool(tc["function"]["name"], args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id") or f"call_{round_i}_{tc['function']['name']}",
                "content": result,
            })

    Path(output_path).write_text(json.dumps(trace, indent=2, default=str))
    summarize(trace)
    return trace


def summarize(trace):
    rounds = trace.get("rounds") or []
    total_calls = 0
    print("=" * 72)
    print(f"model={trace['model']}  parallel_tool_calls={trace['parallel_tool_calls']}")
    print(f"temperature={trace['temperature']}  max_rounds={trace['max_rounds']}")
    print(f"system_prompt={trace['system_prompt_chars']} chars")
    print("=" * 72)
    for r in rounds:
        n = len(r["tool_calls"])
        total_calls += n
        rc = (r.get("reasoning") or "").strip()
        print(f"--- Round {r['round']}  ({r['elapsed_s']}s, finish={r['finish_reason']}, {n} tool_call{'s' if n != 1 else ''}) ---")
        if rc:
            head = rc[:160].replace("\n", " ")
            print(f"    reasoning ({len(rc)} chars): {head}{'…' if len(rc) > 160 else ''}")
        for tc in r["tool_calls"]:
            fn = tc["function"]["name"]
            args_s = tc["function"]["arguments"] or ""
            if len(args_s) > 120:
                args_s = args_s[:117] + "…"
            print(f"    tool_call: {fn}({args_s})")
        if r.get("content"):
            head = r["content"].strip()[:240].replace("\n", " ")
            print(f"    content: {head}{'…' if len(r['content']) > 240 else ''}")
    print("=" * 72)
    print(f"TOTAL: {total_calls} tool calls across {len(rounds)} round(s)")
    if rounds and rounds[-1]["finish_reason"] != "stop":
        print("(loop exited without finish_reason=stop — model may have wanted more rounds)")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=DEFAULT_SERVICE_URL)
    ap.add_argument("--api-key", default=DEFAULT_API_KEY)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--system-prompt", default="default", help="'default' or path to a .txt file")
    ap.add_argument("--max-rounds", type=int, default=8)
    ap.add_argument("--temperature", type=float, default=0.3)
    ap.add_argument("--parallel-tool-calls", dest="parallel", action="store_true", default=True)
    ap.add_argument("--no-parallel-tool-calls", dest="parallel", action="store_false")
    ap.add_argument("--output", default=None, help="JSON trace path (default: tools/traces/<ts>.json)")
    args = ap.parse_args()

    output = args.output
    if not output:
        ts = time.strftime("%Y%m%d-%H%M%S")
        out_dir = REPO_ROOT / "tools" / "traces"
        out_dir.mkdir(parents=True, exist_ok=True)
        tag = "par" if args.parallel else "seq"
        output = str(out_dir / f"{ts}-{tag}.json")

    system_prompt = load_system_prompt(args.system_prompt)
    run(
        url=args.url,
        api_key=args.api_key,
        model=args.model,
        system_prompt=system_prompt,
        user_prompt=USER_PROMPT,
        max_rounds=args.max_rounds,
        parallel_tool_calls=args.parallel,
        temperature=args.temperature,
        output_path=output,
    )
    print(f"\ntrace: {output}")


if __name__ == "__main__":
    main()
