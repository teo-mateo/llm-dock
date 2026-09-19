"""Which configured MCP servers can read a web page, decided from tool schemas.

A server counts as URL-capable only when the tools it advertises include one
taking a `url` string parameter. Entry `id`/`name`/`description` narrow which
servers are worth spawning and never decide the verdict: a `websearch` entry
sounds retrieval-capable and cannot fetch the one URL the user shared, and
reporting it as available is how a shared link ends up answered from prior
knowledge instead of from the page.
"""

CANDIDATE_TOKENS = ("fetch", "url", "browse", "web", "page", "readable")
TEXT_RETURNING_TOKENS = ("markdown", "readable", "text", "content", "article")

PROBE_PARAM = "probe"
URL_FETCH_PROBE = "url-fetch"
PROBE_TIMEOUT = 5.0


def _haystack(server: dict) -> str:
    parts = [str(server.get(key) or "") for key in ("id", "name", "description")]
    return " ".join(parts).lower()


def is_candidate(server: dict) -> bool:
    """Whether entry metadata is promising enough to warrant spawning."""
    hay = _haystack(server)
    return any(token in hay for token in CANDIDATE_TOKENS)


def _bare_name(tool: dict) -> str:
    name = str((tool.get("function") or {}).get("name") or "")
    return name.split("__", 1)[-1]


def _properties(tool: dict) -> dict:
    parameters = (tool.get("function") or {}).get("parameters") or {}
    props = parameters.get("properties")
    return props if isinstance(props, dict) else {}


def _declared_type(prop: dict):
    type_name = prop.get("type")
    if isinstance(type_name, str):
        return type_name
    for key in ("anyOf", "oneOf"):
        for alt in prop.get(key) or []:
            if isinstance(alt, dict) and alt.get("type") == "string":
                return "string"
    return None


def takes_url(tool: dict) -> bool:
    """Whether the tool declares a `url` parameter of string type."""
    prop = _properties(tool).get("url")
    return isinstance(prop, dict) and _declared_type(prop) == "string"


def url_tools(tools: list) -> list:
    return [t for t in tools if isinstance(t, dict) and takes_url(t)]


def is_text_returning(tool: dict) -> bool:
    """Ranking hint only. A screenshot tool takes a url and returns no prose."""
    hay = _bare_name(tool) + " " + str((tool.get("function") or {}).get("description") or "")
    return any(token in hay.lower() for token in TEXT_RETURNING_TOKENS)


def classify(server: dict, tools: list):
    """Classify one probed server, or None when nothing it offers takes a url."""
    fetched = url_tools(tools)
    if not fetched:
        return None
    return {
        "id": server["id"],
        "name": server.get("name") or server["id"],
        "tools": [_bare_name(tool) for tool in fetched],
        "text_returning": any(is_text_returning(tool) for tool in fetched),
    }


def rank(entries: list) -> list:
    """Text-returning servers first, id order within each group."""
    return sorted(entries, key=lambda e: (not e["text_returning"], str(e["id"])))


def _public(entry: dict) -> dict:
    return {"id": entry["id"], "name": entry["name"], "tools": entry["tools"]}


def candidates(servers: list) -> list:
    return [s for s in servers if isinstance(s, dict) and s.get("id") and is_candidate(s)]


def probe(servers: list, discover) -> dict:
    """Probe candidates with `discover(server_id) -> [tool dict]`.

    A discovery error is recorded against that server and never fails the
    whole probe: the caller must be able to tell "nothing is configured" from
    "configured, but it did not answer", which is the difference between
    telling the user to add a tool and telling them to fix one.
    """
    entries = []
    failures = []
    for server in candidates(servers):
        try:
            tools = discover(server["id"])
        except Exception as exc:
            failures.append({"id": server["id"], "error": str(exc) or type(exc).__name__})
            continue
        classified = classify(server, tools if isinstance(tools, list) else [])
        if classified is not None:
            entries.append(classified)
    ranked = rank(entries)
    return {
        "available": bool(ranked),
        "servers": [_public(e) for e in ranked],
        "failures": failures,
    }
