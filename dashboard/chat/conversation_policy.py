import logging
import sqlite3
from dataclasses import dataclass
from typing import Callable

import sampling_params as sampling

from . import run_config

logger = logging.getLogger(__name__)

PROMPT_NOT_FOUND = "Prompt not found"
PROJECT_NOT_FOUND = "Project not found"
SPINOFF_PROJECT = "Spin-off conversations inherit their parent's project"
CONVERSATION_NOT_FOUND = "Conversation not found"


@dataclass(frozen=True)
class PolicyError:
    status: int
    message: str
    code: str | None = None

    def body(self) -> dict:
        body = {"error": self.message}
        if self.code:
            body["code"] = self.code
        return body


@dataclass(frozen=True)
class NewConversation:
    main_service: str
    main_system_prompt: str
    prompt_id: str | None
    project_id: str | None
    reasoning_level: str | None
    sampling_params_json: str | None


def integrity_error(error: sqlite3.IntegrityError) -> PolicyError:
    """A prompt or project deleted between the existence check and the write:
    the DB trigger rejected the orphan reference."""
    if "prompt not found" in str(error):
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
        return PolicyError(400, "main_service is required")

    if "reasoning_level" in data:
        error = _level_error(main_service, data, services)
        if error:
            return error
    error = _sampling_error(data.get("sampling_params"))
    if error:
        return error

    project_id = data.get("project_id")
    if project_id is not None:
        if not isinstance(project_id, str):
            return PolicyError(400, "project_id must be a string or null")
        if data.get("parent_conversation_id"):
            return PolicyError(400, SPINOFF_PROJECT)
        if get_project(project_id) is None:
            return PolicyError(400, PROJECT_NOT_FOUND)

    prompt_id = data.get("prompt_id")
    if prompt_id is not None and not isinstance(prompt_id, str):
        return PolicyError(400, "prompt_id must be a string or null")
    if "main_system_prompt" in data:
        main_system_prompt = data["main_system_prompt"]
        prompt_id = None
    elif prompt_id:
        prompt = get_prompt(prompt_id)
        if prompt is None:
            logger.info("create_conversation: prompt_id %s not found", prompt_id)
            return PolicyError(404, PROMPT_NOT_FOUND)
        main_system_prompt = prompt.content
        prompt_id = prompt.id
    else:
        main_system_prompt = default_prompt()

    return NewConversation(
        main_service=main_service,
        main_system_prompt=main_system_prompt,
        prompt_id=prompt_id,
        project_id=project_id,
        reasoning_level=data.get("reasoning_level"),
        sampling_params_json=sampling.to_storage(data.get("sampling_params")),
    )


def resolve_conversation_update(
    data: dict,
    *,
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
        existing = get_conversation()
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
        if not isinstance(fields["project_id"], str):
            return PolicyError(400, "project_id must be a string or null")
        existing = get_conversation()
        if existing is None:
            return PolicyError(404, CONVERSATION_NOT_FOUND)
        if existing.parent_conversation_id:
            return PolicyError(400, SPINOFF_PROJECT)
        if get_project(fields["project_id"]) is None:
            return PolicyError(400, PROJECT_NOT_FOUND)

    if "prompt_id" in fields and fields["prompt_id"] is not None:
        if not isinstance(fields["prompt_id"], str):
            return PolicyError(400, "prompt_id must be a string or null")
        if "main_system_prompt" in fields:
            fields.pop("prompt_id")
        else:
            prompt = get_prompt(fields["prompt_id"])
            if prompt is None:
                return PolicyError(404, PROMPT_NOT_FOUND)
            fields["main_system_prompt"] = prompt.content

    return fields
