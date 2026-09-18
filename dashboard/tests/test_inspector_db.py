import os
import re
import uuid

import pytest

from inspector.db import MAX_CAPTURES, InspectorDB
from inspector.models import Capture
from inspector.redact import MAX_BODY_CHARS, REDACTED, redact_headers, truncate


@pytest.fixture
def inspector_db():
    return InspectorDB(":memory:")


@pytest.fixture
def inspector_db_file(tmp_path):
    return InspectorDB(str(tmp_path / "inspector.db"))


def make_capture(**overrides) -> Capture:
    capture = Capture(
        id=str(uuid.uuid4()),
        service_name="llamacpp-test",
        model="qwen3-27b",
        template_type="llamacpp",
        method="POST",
        path="/v1/chat/completions",
        status_code=200,
        stream=True,
        request_headers_json={
            "Authorization": "***redacted***",
            "Content-Type": "application/json",
        },
        request_body='{"messages": [{"role": "user", "content": "hi"}]}',
        response_body='data: {"choices": [{"delta": {"content": "hi"}}]}\n\n',
        response_text="Hello there",
        reasoning_text="Thinking about it",
        tool_calls_json='[{"id": "call_1", "name": "search", "arguments": "{}"}]',
        finish_reason="stop",
        prompt_tokens=12,
        completion_tokens=34,
        total_tokens=46,
        ttfb_ms=42,
        duration_ms=1250,
        request_truncated=False,
        response_truncated=False,
    )
    for name, value in overrides.items():
        setattr(capture, name, value)
    return capture


class TestConstruction:
    def test_memory_db_writes_no_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        db = InspectorDB(":memory:")
        db.insert_capture(make_capture())
        assert list(tmp_path.iterdir()) == []

    def test_file_db_creates_file_and_schema_on_first_use(self, tmp_path):
        path = str(tmp_path / "inspector.db")
        db = InspectorDB(path)
        assert os.path.exists(path)
        stored = db.insert_capture(make_capture())
        db_again = InspectorDB(path)
        assert db_again.get_capture(stored.id) is not None


class TestInsertAndGet:
    def test_round_trip_every_field(self, inspector_db):
        capture = make_capture(response_truncated=True)
        stored = inspector_db.insert_capture(capture)
        got = inspector_db.get_capture(capture.id)
        assert got == stored
        assert got.id == capture.id
        assert got.service_name == capture.service_name
        assert got.model == "qwen3-27b"
        assert got.template_type == "llamacpp"
        assert got.method == "POST"
        assert got.path == "/v1/chat/completions"
        assert got.status_code == 200
        assert got.stream is True
        assert got.request_headers_json == {
            "Authorization": "***redacted***",
            "Content-Type": "application/json",
        }
        assert got.request_body == capture.request_body
        assert got.response_body == capture.response_body
        assert got.response_text == "Hello there"
        assert got.reasoning_text == "Thinking about it"
        assert got.tool_calls_json == capture.tool_calls_json
        assert got.finish_reason == "stop"
        assert got.prompt_tokens == 12
        assert got.completion_tokens == 34
        assert got.total_tokens == 46
        assert got.ttfb_ms == 42
        assert got.duration_ms == 1250
        assert got.error is None
        assert got.request_truncated is False
        assert got.response_truncated is True
        assert got.created_at is not None

    def test_round_trip_none_fields(self, inspector_db):
        capture = make_capture(
            model=None,
            template_type=None,
            status_code=None,
            stream=False,
            request_headers_json={},
            request_body="",
            response_body=None,
            response_text=None,
            reasoning_text=None,
            tool_calls_json=None,
            finish_reason=None,
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            ttfb_ms=None,
            duration_ms=None,
        )
        got = inspector_db.get_capture(inspector_db.insert_capture(capture).id)
        assert got.model is None
        assert got.template_type is None
        assert got.status_code is None
        assert got.stream is False
        assert got.request_headers_json == {}
        assert got.request_body == ""
        assert got.response_body is None
        assert got.response_text is None
        assert got.reasoning_text is None
        assert got.tool_calls_json is None
        assert got.finish_reason is None
        assert got.prompt_tokens is None
        assert got.completion_tokens is None
        assert got.total_tokens is None
        assert got.ttfb_ms is None
        assert got.duration_ms is None
        assert got.error is None
        assert got.request_truncated is False
        assert got.response_truncated is False

    def test_get_nonexistent_returns_none(self, inspector_db):
        assert inspector_db.get_capture("missing") is None

    def test_created_at_has_millisecond_precision(self, inspector_db):
        stored = inspector_db.insert_capture(make_capture())
        assert re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", stored.created_at
        )

    def test_insert_honors_explicit_created_at(self, inspector_db):
        stamp = "2026-09-12T10:00:00.123Z"
        stored = inspector_db.insert_capture(make_capture(created_at=stamp))
        assert stored.created_at == stamp


class TestListCaptures:
    def test_newest_first_on_same_second_tie(self, inspector_db):
        stamp = "2026-09-12T10:00:00.000Z"
        ids = [
            inspector_db.insert_capture(make_capture(created_at=stamp)).id
            for _ in range(5)
        ]
        rows, total = inspector_db.list_captures()
        assert total == 5
        assert [row.id for row in rows] == list(reversed(ids))

    def test_filter_by_service(self, inspector_db):
        for _ in range(3):
            inspector_db.insert_capture(make_capture(service_name="svc-a"))
        for _ in range(2):
            inspector_db.insert_capture(make_capture(service_name="svc-b"))
        rows, total = inspector_db.list_captures(service="svc-a")
        assert total == 3
        assert len(rows) == 3
        assert all(row.service_name == "svc-a" for row in rows)

    def test_pagination(self, inspector_db):
        for _ in range(5):
            inspector_db.insert_capture(make_capture(service_name="svc-a"))
        page1, total = inspector_db.list_captures(limit=2, offset=0)
        assert total == 5
        assert len(page1) == 2
        page2, _ = inspector_db.list_captures(limit=2, offset=2)
        page3, _ = inspector_db.list_captures(limit=2, offset=4)
        assert len(page2) == 2
        assert len(page3) == 1
        seen = [row.id for row in page1 + page2 + page3]
        assert len(set(seen)) == 5

    def test_list_rows_carry_no_body_fields(self, inspector_db):
        capture = make_capture()
        inspector_db.insert_capture(capture)
        rows, _ = inspector_db.list_captures()
        row = rows[0]
        assert row.request_body is None
        assert row.response_body is None
        assert row.response_text is None
        assert row.reasoning_text is None
        assert row.request_headers_json is None
        assert row.tool_calls_json is None

    def test_list_rows_keep_summary_fields(self, inspector_db):
        capture = make_capture()
        inspector_db.insert_capture(capture)
        row = inspector_db.list_captures()[0][0]
        assert row.id == capture.id
        assert row.service_name == capture.service_name
        assert row.model == capture.model
        assert row.template_type == capture.template_type
        assert row.method == "POST"
        assert row.path == "/v1/chat/completions"
        assert row.status_code == 200
        assert row.stream is True
        assert row.finish_reason == "stop"
        assert row.prompt_tokens == 12
        assert row.completion_tokens == 34
        assert row.total_tokens == 46
        assert row.ttfb_ms == 42
        assert row.duration_ms == 1250
        assert row.created_at is not None


class TestDelete:
    def test_delete_capture_twice(self, inspector_db):
        capture = make_capture()
        inspector_db.insert_capture(capture)
        assert inspector_db.delete_capture(capture.id) is True
        assert inspector_db.get_capture(capture.id) is None
        assert inspector_db.delete_capture(capture.id) is False

    def test_delete_captures_all(self, inspector_db):
        for _ in range(3):
            inspector_db.insert_capture(make_capture(service_name="svc-a"))
        for _ in range(2):
            inspector_db.insert_capture(make_capture(service_name="svc-b"))
        assert inspector_db.delete_captures() == 5
        rows, total = inspector_db.list_captures()
        assert total == 0
        assert rows == []

    def test_delete_captures_by_service(self, inspector_db):
        for _ in range(3):
            inspector_db.insert_capture(make_capture(service_name="svc-a"))
        for _ in range(2):
            inspector_db.insert_capture(make_capture(service_name="svc-b"))
        assert inspector_db.delete_captures("svc-a") == 3
        rows, total = inspector_db.list_captures()
        assert total == 2
        assert all(row.service_name == "svc-b" for row in rows)

    def test_delete_captures_unknown_service(self, inspector_db):
        assert inspector_db.delete_captures("nobody") == 0


class TestTrim:
    def test_trim_keeps_newest_rows(self, inspector_db):
        stamp = "2026-09-12T10:00:00.000Z"
        ids = [
            inspector_db.insert_capture(make_capture(created_at=stamp)).id
            for _ in range(10)
        ]
        assert inspector_db.trim(3) == 7
        rows, total = inspector_db.list_captures()
        assert total == 3
        assert [row.id for row in rows] == list(reversed(ids))[:3]

    def test_trim_below_cap_is_noop(self, inspector_db):
        for _ in range(2):
            inspector_db.insert_capture(make_capture())
        assert inspector_db.trim(3) == 0
        rows, total = inspector_db.list_captures()
        assert total == 2

    def test_max_captures_constant(self):
        assert MAX_CAPTURES == 2000


class TestRenameAndServices:
    def test_rename_service(self, inspector_db):
        for _ in range(2):
            inspector_db.insert_capture(make_capture(service_name="old-name"))
        inspector_db.insert_capture(make_capture(service_name="other"))
        assert inspector_db.rename_service("old-name", "new-name") == 2
        rows, total = inspector_db.list_captures()
        assert total == 3
        assert all(row.service_name in ("new-name", "other") for row in rows)
        assert inspector_db.rename_service("old-name", "new-name") == 0

    def test_services_with_captures(self, inspector_db):
        inspector_db.insert_capture(make_capture(service_name="svc-b"))
        inspector_db.insert_capture(make_capture(service_name="svc-a"))
        inspector_db.insert_capture(make_capture(service_name="svc-a"))
        assert inspector_db.services_with_captures() == ["svc-a", "svc-b"]

    def test_services_with_captures_empty(self, inspector_db):
        assert inspector_db.services_with_captures() == []


class TestFilePersistence:
    def test_round_trip_through_file(self, inspector_db_file):
        capture = make_capture()
        stored = inspector_db_file.insert_capture(capture)
        got = inspector_db_file.get_capture(capture.id)
        assert got.id == stored.id
        assert got.request_body == capture.request_body
        assert got.request_headers_json == capture.request_headers_json


class TestRedactHeaders:
    def test_authorization_is_redacted(self):
        result = redact_headers({"Authorization": "Bearer key-abc"})
        assert result == {"Authorization": REDACTED}
        assert "key-abc" not in str(result)

    def test_matches_case_insensitively(self):
        result = redact_headers(
            {
                "AUTHORIZATION": "Bearer k",
                "X-Api-Key": "key",
                "Api-Key": "key",
                "X-TOTP-Code": "123456",
                "COOKIE": "s=1",
            }
        )
        assert result == {
            "AUTHORIZATION": REDACTED,
            "X-Api-Key": REDACTED,
            "Api-Key": REDACTED,
            "X-TOTP-Code": REDACTED,
            "COOKIE": REDACTED,
        }

    def test_preserves_original_casing_and_other_headers(self):
        headers = {
            "Authorization": "Bearer k",
            "Content-Type": "application/json",
            "X-Custom": "value",
        }
        result = redact_headers(headers)
        assert list(result.keys()) == ["Authorization", "Content-Type", "X-Custom"]
        assert result["Authorization"] == REDACTED
        assert result["Content-Type"] == "application/json"
        assert result["X-Custom"] == "value"

    def test_without_sensitive_headers_is_unchanged(self):
        headers = {"Content-Type": "application/json", "Host": "localhost"}
        assert redact_headers(headers) == headers


class TestTruncate:
    def test_under_cap_unchanged(self):
        text, truncated = truncate("hello")
        assert text == "hello"
        assert truncated is False

    def test_exactly_at_cap_not_flagged(self):
        text = "x" * MAX_BODY_CHARS
        out, truncated = truncate(text)
        assert out == text
        assert truncated is False

    def test_over_cap_is_cut_and_marked(self):
        text = "x" * (MAX_BODY_CHARS + 10)
        out, truncated = truncate(text)
        assert truncated is True
        assert out == "x" * MAX_BODY_CHARS + "\n…[truncated by llm-dock inspector]"
        assert len(out) > MAX_BODY_CHARS

    def test_custom_cap(self):
        out, truncated = truncate("abcdefghij", cap=5)
        assert truncated is True
        assert out == "abcde\n…[truncated by llm-dock inspector]"

    def test_max_body_chars_constant(self):
        assert MAX_BODY_CHARS == 1_000_000
