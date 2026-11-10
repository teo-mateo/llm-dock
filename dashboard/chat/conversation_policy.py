import logging
import sqlite3
from dataclasses import dataclass
from typing import Callable

import sampling_params as sampling

from . import run_config
from .db import PROMPT_ORPHAN_MARKER
from .outcomes import PolicyError

logger = logging.getLogger(__name__)

PROMPT_NOT_FOUND = "Prompt not found"
PROJECT_NOT_FOUND = "Project not found"
CONVERSATION_NOT_FOUND = "Conversation not found"
SPINOFF_PROJECT = "Spin-off conversations inherit their parent's project"
MAIN_SERVICE_REQUIRED = "main_service is required"
PROJECT_ID_TYPE = "project_id must be a string or null"
PROMPT_ID_TYPE = "prompt_id must be a string or null"


@dataclass(frozen=True)
class NewConversation:
    main_service: str
    main_system_prompt: str
    prompt_id: str | None
    project_id: str | None
    reasoning_level: str | None
    sampling_params_json: str | None


@dataclass(frozen=True)
class PromptChoice:
    text: str | None
    prompt_id: str | None


def integrity_error(error: sqlite3.IntegrityError) -> PolicyError:
    """A prompt or project deleted between the existence check and the write:
    the DB trigger rejected the orphan reference."""
    if PROMPT_ORPHAN_MARKER in str(error):
        return PolicyError(404, PROMPT_NOT_FOUND)
    return PolicyError(400, PROJECT_NOT_FOUND)


def _level_error(main_service, data, services) -> PolicyError | None:
    message = run_config.reasoning_level_error(main_service, data["reasoning_level"], services)
    if message:
        return PolicyError(400, message, run_config.INVALID_LEVEL_CODE)
    return None


def _sampling_error(value) -> PolicyError | None:
    message = run_config.sampling_params_error(value)
    if message:
        return PolicyError(400, message, run_config.INVALID_SAMPLING_CODE)
    return None


def _project_id_type_error(project_id) -> PolicyError | None:
    if isinstance(project_id, str):
        return None
    return PolicyError(400, PROJECT_ID_TYPE)


def _check_project(project_id: str, *, is_spinoff: bool, get_project: Callable) -> PolicyError | None:
    if is_spinoff:
        return PolicyError(400, SPINOFF_PROJECT)
    if get_project(project_id) is None:
        return PolicyError(400, PROJECT_NOT_FOUND)
    return None


def _resolve_prompt(body: dict, get_prompt: Callable) -> PromptChoice | PolicyError:
    prompt_id = body.get("prompt_id")
    if prompt_id is not None and not isinstance(prompt_id, str):
        return PolicyError(400, PROMPT_ID_TYPE)
    if "main_system_prompt" in body:
        return PromptChoice(body["main_system_prompt"], None)
    if prompt_id is None:
        return PromptChoice(None, None)
    prompt = get_prompt(prompt_id)
    if prompt is None:
        logger.info("prompt_id %s not found", prompt_id)
        return PolicyError(404, PROMPT_NOT_FOUND)
    return PromptChoice(prompt.content, prompt.id)


def resolve_new_conversation(
    data: dict,
    *,
    get_prompt: Callable,
    get_project: Callable,
    default_prompt: Callable[[], str],
    services=None,
) -> NewConversation | PolicyError:
    """Validate a create body and resolve the fields that carry policy.

    System prompt precedence: an explicit main_system_prompt wins outright and
    establishes no prompt reference; else a prompt_id resolves that managed
    prompt's content (404 when missing) and is recorded; else the global
    default. The id is stored only where the text was resolved from it.
    """
    main_service = data.get("main_service")
    if not main_service:
        return PolicyError(400, MAIN_SERVICE_REQUIRED)

    if "reasoning_level" in data:
        error = _level_error(main_service, data, services)
        if error:
            return error
    error = _sampling_error(data.get("sampling_params"))
    if error:
        return error

    project_id = data.get("project_id")
    if project_id is not None:
        error = _project_id_type_error(project_id) or _check_project(
            project_id, is_spinoff=bool(data.get("parent_conversation_id")), get_project=get_project
        )
        if error:
            return error

    prompt = _resolve_prompt(data, get_prompt)
    if isinstance(prompt, PolicyError):
        return prompt

    return NewConversation(
        main_service=main_service,
        main_system_prompt=default_prompt() if prompt.text is None else prompt.text,
        prompt_id=prompt.prompt_id,
        project_id=project_id,
        reasoning_level=data.get("reasoning_level"),
        sampling_params_json=sampling.to_storage(data.get("sampling_params")),
    )


def resolve_conversation_update(
    data: dict,
    *,
    conv_id: str,
    get_conversation: Callable,
    get_prompt: Callable,
    get_project: Callable,
    services=None,
) -> dict | PolicyError:
    """Validate an update body and return the fields to store.

    A level must be offered by the service the conversation ends up on, which
    is the requested main_service when both keys arrive; null clears it.
    sampling_params replaces the stored blob (null and {} both clear it to
    NULL). project_id null detaches; a non-null id must name an existing
    project and only root conversations can be assigned. prompt_id null
    detaches (the stored text stays); a non-null id resolves its content into
    main_system_prompt unless the body carries main_system_prompt, which wins
    and drops the reference, as on create.
    """
    fields = dict(data)

    if "reasoning_level" in fields and fields["reasoning_level"] is not None:
        existing = get_conversation(conv_id)
        if existing is None:
            return PolicyError(404, CONVERSATION_NOT_FOUND)
        error = _level_error(fields.get("main_service") or existing.main_service, fields, services)
        if error:
            return error

    if "sampling_params" in fields:
        error = _sampling_error(fields["sampling_params"])
        if error:
            return error
        fields["sampling_params_json"] = sampling.to_storage(fields.pop("sampling_params"))

    if "project_id" in fields and fields["project_id"] is not None:
        error = _project_id_type_error(fields["project_id"])
        if error:
            return error
        existing = get_conversation(conv_id)
        if existing is None:
            return PolicyError(404, CONVERSATION_NOT_FOUND)
        error = _check_project(
            fields["project_id"], is_spinoff=bool(existing.parent_conversation_id), get_project=get_project
        )
        if error:
            return error

    if "prompt_id" in fields and fields["prompt_id"] is not None:
        prompt = _resolve_prompt(fields, get_prompt)
        if isinstance(prompt, PolicyError):
            return prompt
        if prompt.prompt_id is None:
            fields.pop("prompt_id")
        else:
            fields["main_system_prompt"] = prompt.text

    return fields
