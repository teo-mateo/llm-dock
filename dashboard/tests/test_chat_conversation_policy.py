import os
import sqlite3
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat import conversation_policy as policy
from chat.conversation_policy import NewConversation
from chat.outcomes import PolicyError
from reasoning_levels import parse_levels

SERVICES = lambda: [{"name": "svc", "reasoning_levels": parse_levels("off,low")}]
PROMPTS = {"p1": SimpleNamespace(id="p1", content="managed text")}
PROJECTS = {"proj": object()}
DEFAULT = "global default"


def _new(data, **overrides):
    kwargs = dict(
        get_prompt=PROMPTS.get,
        get_project=PROJECTS.get,
        default_prompt=lambda: DEFAULT,
        services=SERVICES,
    )
    kwargs.update(overrides)
    return policy.resolve_new_conversation(data, **kwargs)


def _update(data, existing=SimpleNamespace(main_service="svc", parent_conversation_id=None), **overrides):
    kwargs = dict(
        conv_id="c1",
        get_conversation=lambda conv_id: existing,
        get_prompt=PROMPTS.get,
        get_project=PROJECTS.get,
        services=SERVICES,
    )
    kwargs.update(overrides)
    return policy.resolve_conversation_update(data, **kwargs)


class TestNewConversation:
    def test_main_service_is_required(self):
        assert _new({}) == PolicyError(400, "main_service is required")

    def test_body_prompt_text_wins_and_establishes_no_reference(self):
        out = _new({"main_service": "svc", "main_system_prompt": "mine", "prompt_id": "p1"})

        assert (out.main_system_prompt, out.prompt_id) == ("mine", None)

    def test_a_prompt_id_resolves_its_content_and_is_recorded(self):
        out = _new({"main_service": "svc", "prompt_id": "p1"})

        assert (out.main_system_prompt, out.prompt_id) == ("managed text", "p1")

    def test_without_either_the_global_default_is_used_and_no_id_recorded(self):
        out = _new({"main_service": "svc"})

        assert (out.main_system_prompt, out.prompt_id) == (DEFAULT, None)

    def test_an_empty_prompt_id_names_no_prompt_and_is_a_404(self):
        assert _new({"main_service": "svc", "prompt_id": ""}) == PolicyError(404, "Prompt not found")

    def test_a_missing_prompt_is_a_404(self):
        assert _new({"main_service": "svc", "prompt_id": "nope"}) == PolicyError(404, "Prompt not found")

    def test_a_non_string_prompt_id_is_a_400(self):
        assert _new({"main_service": "svc", "prompt_id": 5}).status == 400

    @pytest.mark.parametrize(
        "extra,expected",
        [
            ({"project_id": "proj"}, None),
            ({"project_id": 7}, PolicyError(400, "project_id must be a string or null")),
            ({"project_id": "proj", "parent_conversation_id": "x"}, PolicyError(400, policy.SPINOFF_PROJECT)),
            ({"project_id": "gone"}, PolicyError(400, "Project not found")),
        ],
    )
    def test_project_membership_rules(self, extra, expected):
        out = _new({"main_service": "svc", **extra})

        if expected is None:
            assert out.project_id == "proj"
        else:
            assert out == expected

    def test_an_unoffered_level_carries_the_level_code(self):
        out = _new({"main_service": "svc", "reasoning_level": "ultra"})

        assert out.status == 400 and out.code == "invalid_reasoning_level"

    def test_a_null_or_offered_level_is_accepted(self):
        assert _new({"main_service": "svc", "reasoning_level": None}).reasoning_level is None
        assert _new({"main_service": "svc", "reasoning_level": "low"}).reasoning_level == "low"

    def test_a_bad_sampling_blob_carries_the_sampling_code(self):
        out = _new({"main_service": "svc", "sampling_params": {"temperature": 99}})

        assert out.status == 400 and out.code == "invalid_sampling_params"

    def test_sampling_is_stored_as_one_blob_and_empty_is_null(self):
        assert _new({"main_service": "svc", "sampling_params": {"seed": 1}}).sampling_params_json is not None
        assert _new({"main_service": "svc", "sampling_params": {}}).sampling_params_json is None
        assert _new({"main_service": "svc"}).sampling_params_json is None

    def test_checks_run_in_a_stable_order(self):
        out = _new({"main_service": "svc", "reasoning_level": "ultra", "sampling_params": {"temperature": 99}})

        assert out.code == "invalid_reasoning_level"

    def test_the_result_is_a_plain_value(self):
        assert isinstance(_new({"main_service": "svc"}), NewConversation)


class TestUpdate:
    def test_fields_pass_through_untouched_when_nothing_carries_policy(self):
        assert _update({"title": "t"}) == {"title": "t"}

    def test_the_conversation_is_looked_up_by_id(self):
        seen = []

        def lookup(conv_id):
            seen.append(conv_id)
            return SimpleNamespace(main_service="svc", parent_conversation_id=None)

        _update({"reasoning_level": "low"}, get_conversation=lookup)

        assert seen == ["c1"]

    def test_the_input_is_not_mutated(self):
        data = {"sampling_params": {"seed": 1}}

        _update(data)

        assert data == {"sampling_params": {"seed": 1}}

    def test_a_level_is_checked_against_the_requested_service_when_both_arrive(self):
        services = lambda: [{"name": "other", "reasoning_levels": parse_levels("off,xhigh")}]

        assert _update({"reasoning_level": "xhigh", "main_service": "other"}, services=services) == {
            "reasoning_level": "xhigh", "main_service": "other",
        }
        assert _update({"reasoning_level": "xhigh"}, services=services).code == "invalid_reasoning_level"

    def test_a_level_on_a_missing_conversation_is_a_404(self):
        assert _update({"reasoning_level": "low"}, existing=None) == PolicyError(404, "Conversation not found")

    def test_a_null_level_clears_without_a_lookup(self):
        out = _update({"reasoning_level": None}, get_conversation=lambda conv_id: pytest.fail("looked up"))

        assert out == {"reasoning_level": None}

    @pytest.mark.parametrize("value", [None, {}])
    def test_sampling_params_replace_the_blob_and_empty_clears_it(self, value):
        assert _update({"sampling_params": value}) == {"sampling_params_json": None}

    def test_sampling_params_become_the_stored_blob(self):
        out = _update({"sampling_params": {"seed": 1}})

        assert "sampling_params" not in out and out["sampling_params_json"] is not None

    def test_project_rules_on_update(self):
        assert _update({"project_id": None}) == {"project_id": None}
        assert _update({"project_id": "proj"}) == {"project_id": "proj"}
        assert _update({"project_id": 3}).status == 400
        assert _update({"project_id": 3}, existing=None).status == 400
        assert _update({"project_id": "gone"}) == PolicyError(400, "Project not found")
        assert _update({"project_id": "proj"}, existing=None) == PolicyError(404, "Conversation not found")

    def test_a_spinoff_cannot_be_assigned_a_project(self):
        spinoff = SimpleNamespace(main_service="svc", parent_conversation_id="root")

        assert _update({"project_id": "proj"}, existing=spinoff) == PolicyError(400, policy.SPINOFF_PROJECT)

    def test_prompt_id_resolves_into_the_prompt_text(self):
        assert _update({"prompt_id": "p1"}) == {"prompt_id": "p1", "main_system_prompt": "managed text"}

    def test_body_text_wins_over_a_prompt_id_and_drops_the_reference(self):
        assert _update({"prompt_id": "p1", "main_system_prompt": "mine"}) == {"main_system_prompt": "mine"}

    def test_a_null_prompt_id_detaches_and_keeps_the_stored_text(self):
        assert _update({"prompt_id": None}) == {"prompt_id": None}

    def test_prompt_id_errors(self):
        assert _update({"prompt_id": "nope"}) == PolicyError(404, "Prompt not found")
        assert _update({"prompt_id": 4}).status == 400


class TestIntegrityError:
    def test_a_prompt_deleted_mid_write_is_a_404(self):
        err = sqlite3.IntegrityError("prompt not found")

        assert policy.integrity_error(err) == PolicyError(404, "Prompt not found")

    def test_the_marker_is_the_one_the_db_trigger_raises(self):
        from chat.db import ChatDB
        from chat.models import Conversation

        db = ChatDB(":memory:")
        with pytest.raises(sqlite3.IntegrityError) as raised:
            db.create_conversation(Conversation(id="c", title="t", main_service="s", prompt_id="ghost"))

        assert policy.integrity_error(raised.value) == PolicyError(404, "Prompt not found")

    def test_anything_else_is_a_project_not_found(self):
        err = sqlite3.IntegrityError("FOREIGN KEY constraint failed")

        assert policy.integrity_error(err) == PolicyError(400, "Project not found")


def test_the_error_body_carries_a_code_only_when_there_is_one():
    assert PolicyError(400, "x").body() == {"error": "x"}
    assert PolicyError(400, "x", "c").body() == {"error": "x", "code": "c"}


def test_the_http_helper_maps_an_outcome_to_json_and_status():
    from flask import Flask
    from chat import http

    with Flask(__name__).app_context():
        response, status = http.error_response(PolicyError(409, "busy", "code"))

    assert status == 409 and response.get_json() == {"error": "busy", "code": "code"}
