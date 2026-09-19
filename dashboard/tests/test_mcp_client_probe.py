"""`MCPClientManager.discover_bounded` — the probe's discovery seam (issue 255)."""

import concurrent.futures
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat import mcp_client
from chat.mcp_client import MCPClientManager


@pytest.fixture
def manager(monkeypatch):
    mgr = MCPClientManager()
    monkeypatch.setattr(mcp_client, "get_server_config", lambda sid: {"command": ["/bin/true"]} if sid == "webfetch" else None)
    return mgr


def _record_discovery(monkeypatch, mgr, tools):
    calls = []

    async def fake(config, server_id):
        calls.append(server_id)
        return tools

    monkeypatch.setattr(mgr, "_discover_tools", fake)
    return calls


def test_a_warm_cache_is_reused_without_contacting_the_server(monkeypatch, manager):
    cached = [{"function": {"name": "webfetch__fetch_readable"}}]
    manager._tools_cache["webfetch"] = cached
    calls = _record_discovery(monkeypatch, manager, [])
    assert manager.discover_bounded("webfetch", 5.0) is cached
    assert calls == []


def test_a_cold_probe_populates_the_cache(monkeypatch, manager):
    tools = [{"function": {"name": "webfetch__fetch_readable"}}]
    calls = _record_discovery(monkeypatch, manager, tools)
    assert manager.discover_bounded("webfetch", 5.0) == tools
    assert calls == ["webfetch"]
    assert manager._tools_cache["webfetch"] == tools


def test_a_timeout_propagates_and_leaves_nothing_cached(monkeypatch, manager):
    def explode(coro, timeout):
        coro.close()
        raise concurrent.futures.TimeoutError()

    monkeypatch.setattr(manager, "_run_async", explode)
    with pytest.raises(concurrent.futures.TimeoutError):
        manager.discover_bounded("webfetch", 1.0)
    assert "webfetch" not in manager._tools_cache


def test_a_server_the_registry_does_not_offer_raises_instead_of_returning_empty(manager):
    with pytest.raises(KeyError):
        manager.discover_bounded("nope", 5.0)


def test_an_empty_tool_list_is_a_real_answer_and_gets_cached(monkeypatch, manager):
    _record_discovery(monkeypatch, manager, [])
    assert manager.discover_bounded("webfetch", 5.0) == []
    assert manager._tools_cache["webfetch"] == []
