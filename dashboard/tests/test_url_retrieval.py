"""Pure classification rules behind `?probe=url-fetch` (issue 255)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat import url_retrieval as ur


def _tool(name: str, properties: dict, description: str = "") -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties},
        },
    }


URL_TOOL = _tool("webfetch__fetch_readable", {"url": {"type": "string"}}, "Fetch readable text")
QUERY_TOOL = _tool("websearch__search", {"query": {"type": "string"}}, "Search the web")
SCREENSHOT_TOOL = _tool("browser-fetch__screenshot_page", {"url": {"type": "string"}}, "Screenshot a page")


def _server(sid: str, name: str = None, description: str = "") -> dict:
    return {"id": sid, "name": name or sid, "description": description, "icon": "fa-x"}


def _discover(table: dict, raises: tuple = ()):
    def discover(server_id: str) -> list:
        if server_id in raises:
            raise RuntimeError(f"boom: {server_id}")
        return table.get(server_id, [])

    return discover


# -- takes_url ---------------------------------------------------------------


def test_string_url_parameter_makes_a_tool_url_capable():
    assert ur.takes_url(URL_TOOL) is True


def test_a_query_parameter_is_not_a_url_parameter():
    assert ur.takes_url(QUERY_TOOL) is False


def test_a_non_string_url_parameter_is_not_url_capable():
    assert ur.takes_url(_tool("x__t", {"url": {"type": "integer"}})) is False


def test_an_optional_string_url_parameter_counts():
    optional = _tool(
        "x__t",
        {"url": {"anyOf": [{"type": "string"}, {"type": "null"}]}},
    )
    assert ur.takes_url(optional) is True


def test_a_tool_with_no_schema_at_all_is_not_url_capable():
    assert ur.takes_url({"type": "function", "function": {"name": "x__t"}}) is False
    assert ur.takes_url({"function": {}}) is False


def test_url_tools_skips_entries_that_are_not_tool_objects():
    assert ur.url_tools([URL_TOOL, None, "junk", 7]) == [URL_TOOL]


def test_url_property_in_a_nested_object_does_not_count():
    nested = _tool("x__t", {"request": {"type": "object", "properties": {"url": {"type": "string"}}}})
    assert ur.takes_url(nested) is False


# -- candidate filter --------------------------------------------------------


@pytest.mark.parametrize("sid,name,description", [
    ("webfetch", "WebFetch", "Fetch a web page as readable text"),
    ("browser-fetch", "Browser Fetch", "Render a page in a headless browser"),
    ("websearch", "Web Search", "Search the web"),
])
def test_the_names_this_machine_actually_uses_are_candidates(sid, name, description):
    assert ur.is_candidate(_server(sid, name, description)) is True


def test_a_knowledge_base_entry_is_not_a_candidate():
    server = _server("ragflow", "RagFlow", "Query the local knowledge base over HTTP")
    assert ur.is_candidate(server) is False


def test_candidate_check_survives_missing_metadata():
    assert ur.is_candidate({"id": "x"}) is False


# -- probe -------------------------------------------------------------------


def test_probe_reports_a_server_whose_tools_take_a_url():
    servers = [_server("webfetch", "WebFetch", "Fetch a web page")]
    result = ur.probe(servers, _discover({"webfetch": [URL_TOOL, QUERY_TOOL]}))
    assert result["available"] is True
    assert result["servers"] == [{"id": "webfetch", "name": "WebFetch", "tools": ["fetch_readable"]}]
    assert result["failures"] == []


def test_probe_rejects_a_candidate_whose_tools_only_take_a_query():
    result = ur.probe([_server("websearch", "Web Search", "Search the web")], _discover({"websearch": [QUERY_TOOL]}))
    assert result["available"] is False
    assert result["servers"] == []
    assert result["failures"] == []


def test_probe_never_spawns_a_non_candidate():
    calls = []

    def discover(server_id: str) -> list:
        calls.append(server_id)
        return []

    ur.probe([_server("ragflow", "RagFlow", "Query the knowledge base")], discover)
    assert calls == []


def test_discovery_failure_is_attributed_to_its_server_and_keeps_the_rest():
    servers = [
        _server("brokenfetch", "Broken Fetch", "Fetch pages"),
        _server("webfetch", "WebFetch", "Fetch a web page"),
    ]
    result = ur.probe(servers, _discover({"webfetch": [URL_TOOL]}, raises=("brokenfetch",)))
    assert result["available"] is True
    assert [s["id"] for s in result["servers"]] == ["webfetch"]
    assert result["failures"] == [{"id": "brokenfetch", "error": "boom: brokenfetch"}]


def test_a_broken_registry_alone_still_reads_as_unavailable_not_broken():
    result = ur.probe([_server("webfetch", "WebFetch", "Fetch a web page")], _discover({}, raises=("webfetch",)))
    assert result["available"] is False
    assert result["servers"] == []
    assert len(result["failures"]) == 1


def test_text_returning_servers_rank_above_a_url_tool_with_no_prose():
    servers = [
        _server("browser-fetch", "Browser Fetch", "Browse pages"),
        _server("webfetch", "WebFetch", "Fetch a web page"),
    ]
    table = {"browser-fetch": [SCREENSHOT_TOOL], "webfetch": [URL_TOOL]}
    result = ur.probe(servers, _discover(table))
    assert [s["id"] for s in result["servers"]] == ["webfetch", "browser-fetch"]


def test_entries_expose_only_id_name_and_tools():
    result = ur.probe([_server("webfetch", "WebFetch", "Fetch a web page")], _discover({"webfetch": [URL_TOOL]}))
    assert set(result["servers"][0]) == {"id", "name", "tools"}


def test_probe_survives_a_discover_that_returns_nonsense():
    result = ur.probe([_server("webfetch", "WebFetch", "Fetch a web page")], lambda sid: None)
    assert result["available"] is False


def test_probe_on_an_empty_registry_is_just_unavailable():
    assert ur.probe([], _discover({})) == {"available": False, "servers": [], "failures": []}
