import logging
from dataclasses import dataclass
from typing import Callable

from reasoning_levels import ENGINE_OPENROUTER, ENGINE_PROVIDER, find_level, format_levels, parse_levels
import sampling_params as sampling

from . import openrouter, providers

logger = logging.getLogger(__name__)

ServiceLookup = Callable[[], list]


def default_services() -> list:
    from docker_utils import get_docker_services

    return get_docker_services()


def effective_project_id(conv, resolve_project_id):
    """The conversation's effective project. Membership is root-only: a
    spin-off keeps project_id NULL and follows its root ancestor.

    This is the SINGLE owner of project resolution for a chat turn: it is
    called once when the run is created, and the result is snapshotted into
    the run (manager scoping AND tool auto-enable both consume the same
    value), so a root moved mid-turn cannot split scope from toggles.
    """
    if conv.project_id:
        return conv.project_id
    if conv.parent_conversation_id:
        return resolve_project_id(conv.id)
    return None


def service_reasoning_levels(service_name, services: ServiceLookup | None = None):
    """Levels a service currently declares, as parsed dicts ([] when none).

    Reads the same payload the chat picker uses, so the ladder offered and the
    ladder enforced cannot drift, and stopped services resolve like running ones.
    For an ``openrouter:`` name the ladder captured when the model joined the curated
    shortlist stands in for a declaration, read through ``openrouter.ladder_for_model``
    so this enforcement point and the request builder cannot disagree.
    """
    if openrouter.is_openrouter_service(service_name):
        return parse_levels(openrouter.ladder_for_model(openrouter.model_id(service_name)))
    if providers.is_provider_service(service_name):
        return []
    try:
        payload = (services or default_services)()
    except Exception:
        logger.exception("reasoning-level lookup failed for service %s", service_name)
        return []
    for svc in payload:
        if svc["name"] == service_name:
            return svc.get("reasoning_levels") or []
    return []


# Carried on the 400 so a client can tell a level rejection from any other bad
# request; the composer retries a create on this code and nothing else.
INVALID_LEVEL_CODE = "invalid_reasoning_level"


def reasoning_level_error(main_service, reasoning_level, services: ServiceLookup | None = None):
    """Rejection message for a level the service does not offer, else None.

    `null` is always accepted: it means "say nothing to the model".
    """
    if reasoning_level is None:
        return None
    if not isinstance(reasoning_level, str):
        return "reasoning_level must be a string or null"
    levels = service_reasoning_levels(main_service, services)
    if find_level(levels, reasoning_level) is None:
        return (
            f"reasoning_level '{reasoning_level}' is not offered by service "
            f"'{main_service}' (declared: {format_levels(levels) or 'none'})"
        )
    return None


def effective_reasoning_level(conv, services: ServiceLookup | None = None):
    """(level to apply, note) for a run — the second enforcement point.

    The service can have lost a stored level since the write path checked it, so
    nothing undeclared is ever sent. The column is left alone: the drop is for
    this run only, so switching the model back restores the choice. The note
    rides the run_started frame so the UI can say the level was ignored.
    """
    stored = getattr(conv, "reasoning_level", None)
    if not stored:
        return None, None
    if find_level(service_reasoning_levels(conv.main_service, services), stored) is not None:
        return stored, None
    logger.info(
        "run for conversation %s: reasoning level '%s' no longer offered by '%s', ignored",
        conv.id, stored, conv.main_service,
    )
    return None, f"Reasoning level '{stored}' is not offered by this model and was ignored"


# Carried on the 400 for the same reason as the level code: the composer retries
# a rejected save on this code alone, never on prose.
INVALID_SAMPLING_CODE = "invalid_sampling_params"


def service_engine(service_name, services: ServiceLookup | None = None):
    """Engine (``template_type``) a service runs on, None when it is unknown.

    Reads the same service payload the chat picker uses, so what the composer
    offers and what the runner sends are the same answer - and a stopped service
    resolves like a running one, which is what lets params be saved before the
    model starts. See the ``template_type`` gotcha in AGENTS.md: an engine that
    does not travel with the service silently unmaps every per-engine field.
    """
    if openrouter.is_openrouter_service(service_name):
        return ENGINE_OPENROUTER
    if providers.is_provider_service(service_name):
        return ENGINE_PROVIDER
    try:
        payload = (services or default_services)()
    except Exception:
        logger.exception("engine lookup failed for service %s", service_name)
        return None
    for svc in payload:
        if svc["name"] == service_name:
            return svc.get("template_type") or None
    return None


def sampling_params_error(value):
    """Rejection message for a request body's sampling params, else None.

    Absent, null and empty are all accepted: they mean "send nothing", which is
    the pre-feature request rather than a change to it.
    """
    valid, errors = sampling.validate(value)
    if valid:
        return None
    return "; ".join(errors)


def effective_sampling_params(conv, services: ServiceLookup | None = None):
    """(params to apply, note) for a run — the second enforcement point.

    The engine can have changed under a stored set since the write path checked
    it, so a field the current engine cannot take is dropped for this run only and
    the column is left alone; switching the model back restores the choice. The
    note rides the run_started frame naming each dropped field, because a silently
    dropped temperature is otherwise indistinguishable from a model that ignored
    it - which is the outcome the whole two-enforcement-points design exists to
    avoid.
    """
    stored = sampling.from_storage(getattr(conv, "sampling_params_json", None))
    if not stored:
        return None, None
    applicable, dropped = sampling.drop_unsupported(stored, service_engine(conv.main_service, services))
    if not dropped:
        return applicable, None
    logger.info(
        "run for conversation %s: sampling params %s not applicable to '%s', ignored",
        conv.id, ",".join(dropped), conv.main_service,
    )
    return applicable, (
        f"Sampling params ignored by this model: {', '.join(dropped)}"
    )


@dataclass(frozen=True)
class RunConfig:
    """Everything a run snapshots at creation. A mid-run edit affects only the
    next run, and a note is non-None exactly when something was dropped."""

    project_id: str | None
    reasoning_level: str | None
    reasoning_note: str | None
    sampling_params: dict | None
    sampling_note: str | None

    def started_extra(self) -> dict:
        extra = {"reasoning_level": self.reasoning_level,
                 "sampling_params": self.sampling_params}
        if self.reasoning_note:
            extra["reasoning_level_note"] = self.reasoning_note
        if self.sampling_note:
            extra["sampling_params_note"] = self.sampling_note
        return extra


def prepare_run_config(conv, project_id, services: ServiceLookup | None = None) -> RunConfig:
    reasoning_level, reasoning_note = effective_reasoning_level(conv, services)
    sampling_params, sampling_note = effective_sampling_params(conv, services)
    return RunConfig(project_id, reasoning_level, reasoning_note, sampling_params, sampling_note)
