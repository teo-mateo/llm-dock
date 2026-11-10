import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat import run_config
from chat.models import Conversation
from reasoning_levels import ENGINE_OPENROUTER, ENGINE_PROVIDER, parse_levels

SERVICES = lambda: [
    {"name": "llamacpp-a", "template_type": "llamacpp", "reasoning_levels": parse_levels("off,low")},
    {"name": "vllm-b", "template_type": "vllm", "reasoning_levels": []},
]


def _conv(service="llamacpp-a", level=None, params=None, **extra):
    return Conversation(
        id="c", title="t", main_service=service, reasoning_level=level,
        sampling_params_json=params, **extra,
    )


def test_a_service_lookup_failure_is_a_missing_declaration_not_an_error():
    def broken():
        raise RuntimeError("docker is down")

    assert run_config.service_reasoning_levels("llamacpp-a", broken) == []
    assert run_config.service_engine("llamacpp-a", broken) is None


def test_remote_services_resolve_without_asking_docker():
    def never():
        raise AssertionError("docker must not be consulted")

    assert run_config.service_engine("openrouter:org/model", never) == ENGINE_OPENROUTER
    assert run_config.service_engine("mistral:large", never) == ENGINE_PROVIDER
    assert run_config.service_reasoning_levels("mistral:large", never) == []


def test_level_error_names_the_service_and_what_it_declares():
    message = run_config.reasoning_level_error("llamacpp-a", "ultra", SERVICES)

    assert "ultra" in message and "llamacpp-a" in message and "off" in message


def test_level_error_accepts_null_and_a_declared_level_and_rejects_a_non_string():
    assert run_config.reasoning_level_error("llamacpp-a", None, SERVICES) is None
    assert run_config.reasoning_level_error("llamacpp-a", "low", SERVICES) is None
    assert run_config.reasoning_level_error("llamacpp-a", 3, SERVICES) == "reasoning_level must be a string or null"


def test_sampling_error_accepts_absent_and_empty_and_rejects_out_of_range():
    assert run_config.sampling_params_error(None) is None
    assert run_config.sampling_params_error({}) is None
    assert run_config.sampling_params_error({"temperature": 99}) is not None


def test_project_id_prefers_the_row_then_the_chain_then_none():
    calls = []

    def resolve(conv_id):
        calls.append(conv_id)
        return "from-chain"

    assert run_config.effective_project_id(_conv(project_id="own"), resolve) == "own"
    assert run_config.effective_project_id(_conv(parent_conversation_id="p"), resolve) == "from-chain"
    assert run_config.effective_project_id(_conv(), resolve) is None
    assert calls == ["c"]


def test_prepare_run_config_snapshots_level_params_and_project():
    conv = _conv("llamacpp-a", "low", '{"temperature": 0.3}', project_id="p1")

    cfg = run_config.prepare_run_config(conv, lambda conv_id: None, SERVICES)

    assert cfg.project_id == "p1"
    assert (cfg.reasoning_level, cfg.reasoning_note) == ("low", None)
    assert cfg.sampling_params == {"temperature": 0.3} and cfg.sampling_note is None


def test_prepare_run_config_resolves_a_spinoffs_project_through_the_chain():
    cfg = run_config.prepare_run_config(
        _conv(parent_conversation_id="root"), lambda conv_id: "from-chain", SERVICES
    )

    assert cfg.project_id == "from-chain"


def test_started_extra_carries_the_values_and_a_note_only_when_something_was_dropped():
    clean = run_config.prepare_run_config(_conv("llamacpp-a", "low"), lambda i: None, SERVICES)
    assert clean.started_extra() == {"reasoning_level": "low", "sampling_params": None}

    dropped = run_config.prepare_run_config(
        _conv("ghost", "low", '{"top_k": 5}'), lambda i: None, SERVICES
    )
    extra = dropped.started_extra()
    assert extra["reasoning_level"] is None and "low" in extra["reasoning_level_note"]
    assert "top_k" in extra["sampling_params_note"]


def test_one_service_catalog_is_read_per_run_for_both_policies():
    reads = []

    def catalog():
        reads.append(1)
        return SERVICES()

    run_config.prepare_run_config(_conv("llamacpp-a", "low", '{"temperature": 0.3}'), lambda i: None, catalog)

    assert reads == [1]


def test_a_failing_catalog_is_attempted_once_and_both_policies_degrade():
    reads = []

    def broken():
        reads.append(1)
        raise RuntimeError("docker is down")

    cfg = run_config.prepare_run_config(
        _conv("llamacpp-a", "low", '{"temperature": 0.3}'), lambda i: None, broken
    )

    assert reads == [1]
    assert cfg.reasoning_level is None and cfg.sampling_params is None


def test_a_remote_only_conversation_never_reads_the_catalog():
    def never():
        raise AssertionError("docker must not be consulted")

    cfg = run_config.prepare_run_config(_conv("mistral:large", None), lambda i: None, never)

    assert cfg.reasoning_level is None
