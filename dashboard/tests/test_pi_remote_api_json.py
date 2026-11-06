from dataclasses import fields

from pi_remote.api_json import MAX_MESSAGE_TEXT, page_json, parse_message_body, parse_paging, summary_json
from pi_remote.read_model import EventPage, EventView, SessionSummary


def _summary():
    return SessionSummary(
        session_id="s1",
        instance_id="i1",
        name="probe",
        cwd="/tmp",
        model="mistral/mistral-small-latest",
        thinking_level="high",
        first_seen=1000,
        last_seen=2000,
        ended_at=None,
        end_reason=None,
        live=True,
        state="idle",
        context_percent=10.0,
    )


def test_summary_json_keys_are_field_names():
    payload = summary_json(_summary())
    assert set(payload) == {field.name for field in fields(SessionSummary)}
    assert payload["session_id"] == "s1"
    assert payload["live"] is True


def test_page_json_shape():
    page = EventPage(
        events=[EventView(1, "state", 1000, {"state": "idle"})],
        next_after=1,
        has_more=False,
    )
    assert page_json(page) == {
        "events": [{"seq": 1, "type": "state", "ts": 1000, "payload": {"state": "idle"}}],
        "next_after": 1,
        "has_more": False,
    }


def test_parse_paging_defaults():
    assert parse_paging({}) == (0, None, None)
    assert parse_paging({"after": "3"}) == (3, None, None)
    assert parse_paging({"limit": "50"}) == (0, 50, None)


def test_parse_paging_rejects_negative_and_non_int():
    assert parse_paging({"after": "-1"}) == (None, None, "invalid_paging")
    assert parse_paging({"after": "abc"}) == (None, None, "invalid_paging")
    assert parse_paging({"after": "1.5"}) == (None, None, "invalid_paging")
    assert parse_paging({"limit": "-1"}) == (None, None, "invalid_paging")
    assert parse_paging({"limit": "abc"}) == (None, None, "invalid_paging")


def test_parse_paging_rejects_zero_limit():
    assert parse_paging({"limit": "0"}) == (None, None, "invalid_paging")


def test_message_body_valid():
    assert parse_message_body({"text": "hello"}) == ("hello", None)
    assert parse_message_body({"text": "  hello  "}) == ("  hello  ", None)
    assert parse_message_body({"text": "x" * MAX_MESSAGE_TEXT}) == ("x" * MAX_MESSAGE_TEXT, None)


def test_message_body_empty_and_whitespace_invalid():
    assert parse_message_body({"text": ""}) == (None, "invalid_text")
    assert parse_message_body({"text": "   "}) == (None, "invalid_text")


def test_message_body_over_long_invalid():
    assert parse_message_body({"text": "x" * (MAX_MESSAGE_TEXT + 1)}) == (None, "invalid_text")


def test_message_body_non_string_invalid():
    assert parse_message_body({"text": 123}) == (None, "invalid_text")
    assert parse_message_body({"text": None}) == (None, "invalid_text")
    assert parse_message_body({}) == (None, "invalid_text")


def test_message_body_non_object_invalid():
    assert parse_message_body(None) == (None, "invalid_body")
    assert parse_message_body([]) == (None, "invalid_body")
    assert parse_message_body("text") == (None, "invalid_body")
