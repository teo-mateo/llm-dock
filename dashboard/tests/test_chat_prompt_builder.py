"""Unit tests for chat.prompt_builder.build_chat_messages (Phase 1 of #58).

The builder was extracted from _stream_response; these pin its system-prompt
augmentation (tool hints + date line) and its delegation of row->dict shaping
(including image multipart) to build_messages_array.
"""
import datetime
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat import prompt_builder
from chat.models import Message


def _user(content="hi", images_json=None):
    return Message(
        id=str(uuid.uuid4()),
        conversation_id="c",
        role="user",
        content=content,
        images_json=images_json,
        seq=0,
    )


def _system_text(arr):
    assert arr[0]["role"] == "system"
    return arr[0]["content"]


def test_date_line_appended_by_default(monkeypatch):
    monkeypatch.setattr(prompt_builder, "get_tool_hints", lambda s: "")
    arr = prompt_builder.build_chat_messages("You are helpful.", [_user()], [])
    sys_text = _system_text(arr)
    assert sys_text.startswith("You are helpful.\n\n")
    assert "Current date:" in sys_text
    today = datetime.date.today()
    assert today.isoformat() in sys_text
    # The user message is carried through.
    assert arr[1] == {"role": "user", "content": "hi"}


def test_date_line_can_be_disabled(monkeypatch):
    monkeypatch.setattr(prompt_builder, "get_tool_hints", lambda s: "")
    arr = prompt_builder.build_chat_messages("Base.", [_user()], [], include_date_line=False)
    assert _system_text(arr) == "Base."


def test_tool_hints_prepended_before_date_line(monkeypatch):
    monkeypatch.setattr(prompt_builder, "get_tool_hints", lambda servers: f"HINTS for {servers}")
    arr = prompt_builder.build_chat_messages("Base.", [_user()], ["sympy-math"])
    sys_text = _system_text(arr)
    assert "Base." in sys_text
    assert "HINTS for ['sympy-math']" in sys_text
    # Order: base prompt, then hints, then date line.
    assert sys_text.index("Base.") < sys_text.index("HINTS") < sys_text.index("Current date:")


def test_no_hints_when_no_servers(monkeypatch):
    called = {"n": 0}

    def _hints(servers):
        called["n"] += 1
        return "SHOULD NOT APPEAR"

    monkeypatch.setattr(prompt_builder, "get_tool_hints", _hints)
    arr = prompt_builder.build_chat_messages("Base.", [_user()], [])
    assert "SHOULD NOT APPEAR" not in _system_text(arr)
    assert called["n"] == 0  # not consulted when no servers enabled


def test_empty_system_prompt_yields_date_line_only(monkeypatch):
    monkeypatch.setattr(prompt_builder, "get_tool_hints", lambda s: "")
    arr = prompt_builder.build_chat_messages("", [_user()], [])
    # No leading blank lines when there was no base prompt.
    assert _system_text(arr).startswith("Current date:")


def test_images_delegated_to_multipart(monkeypatch):
    monkeypatch.setattr(prompt_builder, "get_tool_hints", lambda s: "")
    msg = _user(content="look", images_json='["data:image/png;base64,AAAA"]')
    arr = prompt_builder.build_chat_messages("", [msg], [], include_date_line=False)
    # System prompt is empty + no date line -> only the user message remains.
    assert len(arr) == 1
    content = arr[0]["content"]
    assert {"type": "text", "text": "look"} in content
    assert {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}} in content
