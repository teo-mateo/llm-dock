import json
import os
import sys
import uuid

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DASHBOARD_TOKEN", "test-token-inspector")

import routes.inspector as inspector_routes
from inspector.db import InspectorDB
from inspector.models import Capture
from routes import inspector_bp

TOKEN = "test-token-inspector"


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


class _FakeSupervisor:
    def __init__(self, rows):
        self._rows = rows

    def status(self):
        return self._rows


def _insert(db, service, n=1, **overrides):
    ids = []
    for i in range(n):
        capture = Capture(
            id=str(uuid.uuid4()),
            service_name=service,
            model="m-1",
            template_type="llamacpp",
            method="POST",
            path="/v1/chat/completions",
            status_code=200,
            stream=True,
            request_headers_json={
                "Authorization": "***redacted***",
                "Content-Type": "application/json",
            },
            request_body='{"model": "m-1", "messages": []}',
            response_body='data: [DONE]\n\n',
            response_text="hi",
            reasoning_text="thinking",
            tool_calls_json=json.dumps(
                [{"id": "call-1", "function": {"name": "search", "arguments": "{}"}}]
            ),
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            ttfb_ms=100,
            duration_ms=2000,
            created_at=f"2026-09-18T20:00:00.{i:03d}Z",
        )
        for name, value in overrides.items():
            setattr(capture, name, value)
        db.insert_capture(capture)
        ids.append(capture.id)
    return ids


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = InspectorDB(str(tmp_path / "inspector.db"))
    app = Flask(__name__)
    app.config["DASHBOARD_TOKEN"] = TOKEN
    app.config["INSPECTOR_DB"] = db
    app.register_blueprint(inspector_bp)
    app.testing = True
    return {"client": app.test_client(), "db": db}


# -- Auth ---------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/inspector/captures"),
        ("get", "/api/inspector/captures/some-id"),
        ("delete", "/api/inspector/captures/some-id"),
        ("delete", "/api/inspector/captures"),
        ("get", "/api/inspector/services"),
    ],
)
def test_requires_bearer_token(env, method, path):
    resp = getattr(env["client"], method)(path)
    assert resp.status_code == 401


# -- GET list -----------------------------------------------------------


def test_list_newest_first(env):
    ids = _insert(env["db"], "svc-a", 5)

    resp = env["client"].get("/api/inspector/captures", headers=_auth())

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 5
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert [row["id"] for row in body["captures"]] == list(reversed(ids))


def test_list_pagination_and_total(env):
    _insert(env["db"], "svc-a", 5)

    page1 = env["client"].get(
        "/api/inspector/captures?limit=2&offset=0", headers=_auth()
    ).get_json()
    page2 = env["client"].get(
        "/api/inspector/captures?limit=2&offset=2", headers=_auth()
    ).get_json()
    page3 = env["client"].get(
        "/api/inspector/captures?limit=2&offset=4", headers=_auth()
    ).get_json()

    assert page1["total"] == 5
    assert page2["total"] == 5
    assert page3["total"] == 5
    assert len(page1["captures"]) == 2
    assert len(page2["captures"]) == 2
    assert len(page3["captures"]) == 1
    seen = {row["id"] for page in (page1, page2, page3) for row in page["captures"]}
    assert len(seen) == 5


def test_limit_clamped_to_200(env):
    _insert(env["db"], "svc-a", 3)
    resp = env["client"].get("/api/inspector/captures?limit=500", headers=_auth())
    body = resp.get_json()
    assert body["limit"] == 200
    assert body["total"] == 3


@pytest.mark.parametrize("query", ["?limit=0", "?limit=-1", "?limit=abc", "?limit=1.5"])
def test_bad_limit_is_400(env, query):
    resp = env["client"].get(f"/api/inspector/captures{query}", headers=_auth())
    assert resp.status_code == 400
    assert "limit" in resp.get_json()["error"]


@pytest.mark.parametrize("query", ["?offset=-1", "?offset=abc"])
def test_bad_offset_is_400(env, query):
    resp = env["client"].get(f"/api/inspector/captures{query}", headers=_auth())
    assert resp.status_code == 400
    assert "offset" in resp.get_json()["error"]


def test_service_filter_and_unknown_service(env):
    _insert(env["db"], "svc-a", 3)
    _insert(env["db"], "svc-b", 2)

    filtered = env["client"].get(
        "/api/inspector/captures?service=svc-a", headers=_auth()
    ).get_json()
    assert filtered["total"] == 3
    assert all(row["service_name"] == "svc-a" for row in filtered["captures"])

    unknown = env["client"].get(
        "/api/inspector/captures?service=nobody", headers=_auth()
    )
    assert unknown.status_code == 200
    body = unknown.get_json()
    assert body["captures"] == []
    assert body["total"] == 0


def test_list_rows_carry_no_body_fields(env):
    _insert(env["db"], "svc-a", 1)

    body = env["client"].get("/api/inspector/captures", headers=_auth()).get_json()
    row = body["captures"][0]
    assert "request_body" not in row
    assert "response_body" not in row
    assert "response_text" not in row
    assert "reasoning_text" not in row
    assert "request_headers" not in row
    assert "tool_calls" not in row
    assert row["stream"] is True
    assert row["request_truncated"] is False
    assert row["response_truncated"] is False


# -- GET detail ---------------------------------------------------------


def test_detail_returns_full_row(env):
    _insert(env["db"], "svc-a", 1)
    capture_id = env["db"].list_captures()[0][0].id

    resp = env["client"].get(f"/api/inspector/captures/{capture_id}", headers=_auth())

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["request_body"] == '{"model": "m-1", "messages": []}'
    assert body["request_headers"] == {
        "Authorization": "***redacted***",
        "Content-Type": "application/json",
    }
    assert body["tool_calls"] == [
        {"id": "call-1", "function": {"name": "search", "arguments": "{}"}}
    ]
    assert body["response_text"] == "hi"
    assert body["reasoning_text"] == "thinking"
    assert body["finish_reason"] == "stop"
    assert body["stream"] is True


def test_detail_null_tool_calls_returns_empty_list(env):
    capture_id = _insert(env["db"], "svc-a", 1, tool_calls_json=None, response_text=None)[0]

    resp = env["client"].get(f"/api/inspector/captures/{capture_id}", headers=_auth())

    assert resp.status_code == 200
    assert resp.get_json()["tool_calls"] == []


def test_detail_malformed_request_body_is_verbatim_string(env):
    raw = '{"model": "m-1", "messages": [truncated'
    capture_id = _insert(env["db"], "svc-a", 1, request_body=raw)[0]

    resp = env["client"].get(f"/api/inspector/captures/{capture_id}", headers=_auth())

    assert resp.status_code == 200
    body = resp.get_json()
    assert isinstance(body["request_body"], str)
    assert body["request_body"] == raw


def test_detail_unknown_id_is_404(env):
    resp = env["client"].get("/api/inspector/captures/nope", headers=_auth())
    assert resp.status_code == 404
    assert "not found" in resp.get_json()["error"]


# -- DELETE -------------------------------------------------------------


def test_delete_one_and_second_call_is_404(env):
    ids = _insert(env["db"], "svc-a", 2)

    resp = env["client"].delete(f"/api/inspector/captures/{ids[0]}", headers=_auth())

    assert resp.status_code == 200
    assert resp.get_json() == {"deleted": 1}
    assert env["client"].get(f"/api/inspector/captures/{ids[0]}", headers=_auth()).status_code == 404

    assert (
        env["client"].delete(f"/api/inspector/captures/{ids[0]}", headers=_auth()).status_code
        == 404
    )
    assert env["client"].get(f"/api/inspector/captures/{ids[1]}", headers=_auth()).status_code == 200


def test_delete_all_by_service_leaves_others(env):
    _insert(env["db"], "svc-a", 3)
    _insert(env["db"], "svc-b", 2)

    resp = env["client"].delete("/api/inspector/captures?service=svc-a", headers=_auth())

    assert resp.status_code == 200
    assert resp.get_json() == {"deleted": 3}
    remaining = env["client"].get("/api/inspector/captures", headers=_auth()).get_json()
    assert remaining["total"] == 2
    assert all(row["service_name"] == "svc-b" for row in remaining["captures"])


def test_delete_all_empties_table(env):
    _insert(env["db"], "svc-a", 2)
    _insert(env["db"], "svc-b", 3)

    resp = env["client"].delete("/api/inspector/captures", headers=_auth())

    assert resp.status_code == 200
    assert resp.get_json() == {"deleted": 5}
    assert env["client"].get("/api/inspector/captures", headers=_auth()).get_json()["total"] == 0


def test_delete_all_unknown_service_deletes_zero(env):
    resp = env["client"].delete("/api/inspector/captures?service=nobody", headers=_auth())
    assert resp.status_code == 200
    assert resp.get_json() == {"deleted": 0}


# -- GET /services ------------------------------------------------------


def test_services_is_union_of_history_and_live_proxies(env, monkeypatch):
    _insert(env["db"], "svc-history", 91)
    _insert(env["db"], "svc-both", 2)
    fake = _FakeSupervisor(
        [
            {
                "service": "svc-live",
                "listen_port": 3317,
                "upstream_port": 34000,
                "running": True,
                "error": None,
            },
            {
                "service": "svc-both",
                "listen_port": 3318,
                "upstream_port": 34001,
                "running": True,
                "error": None,
            },
        ]
    )
    monkeypatch.setattr(inspector_routes, "proxy_supervisor", fake)

    resp = env["client"].get("/api/inspector/services", headers=_auth())

    assert resp.status_code == 200
    services = {row["service_name"]: row for row in resp.get_json()["services"]}
    assert set(services) == {"svc-history", "svc-live", "svc-both"}

    history = services["svc-history"]
    assert history["capture_count"] == 91
    assert history["inspect"] is False
    assert history["listen_port"] is None
    assert history["upstream_port"] is None
    assert history["proxy_running"] is False
    assert history["error"] is None

    live = services["svc-live"]
    assert live["capture_count"] == 0
    assert live["inspect"] is True
    assert live["listen_port"] == 3317
    assert live["upstream_port"] == 34000
    assert live["proxy_running"] is True

    both = services["svc-both"]
    assert both["capture_count"] == 2
    assert both["inspect"] is True


def test_services_reports_failed_bind(env, monkeypatch):
    fake = _FakeSupervisor(
        [
            {
                "service": "svc-broken",
                "listen_port": 3317,
                "upstream_port": 34000,
                "running": False,
                "error": "[Errno 98] Address already in use",
            }
        ]
    )
    monkeypatch.setattr(inspector_routes, "proxy_supervisor", fake)

    resp = env["client"].get("/api/inspector/services", headers=_auth())

    row = resp.get_json()["services"][0]
    assert row["inspect"] is True
    assert row["proxy_running"] is False
    assert row["error"] == "[Errno 98] Address already in use"
    assert row["capture_count"] == 0


def test_services_empty_when_nothing(env, monkeypatch):
    monkeypatch.setattr(inspector_routes, "proxy_supervisor", _FakeSupervisor([]))

    resp = env["client"].get("/api/inspector/services", headers=_auth())

    assert resp.status_code == 200
    assert resp.get_json() == {"services": []}
