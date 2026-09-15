"""Per-conversation sampling parameters: field grammar, ranges and wire mapping.

Pure module, and the single owner of what a stored sampling parameter means, so
validation, payload exposure and request construction cannot disagree — the seam
``reasoning_levels.py`` holds for reasoning levels. Absence is the default state
and it sends nothing: a conversation with no stored parameters produces the
request that existed before this feature, key set and all.

Which fields an engine accepts, and under which name, is measured — never
assumed. The matrix, the command behind every verdict and everything rejected
live in ``docs/plans/chat-sampling-params.md``. An engine absent from a field's
``wire`` map gets nothing and the UI offers nothing, because a field an engine
ignores silently is indistinguishable from a model that chose to ignore it.
"""

import json
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from reasoning_levels import ENGINE_LLAMACPP, ENGINE_VLLM

# One blob rather than a column per knob, so a new knob costs no migration. The
# column needs no size cap of its own: every field is bounded below and `stop`
# carries all the free text, so the per-field bounds already bound the blob.
# Measured ceilings are looser (vLLM takes 8 stop strings, llama.cpp has no
# limit); these are llm-dock's own ceiling, chosen to stay inside both.
MAX_STOP_ENTRIES = 4
MAX_STOP_CHARS = 128

# Both engines address the context limit differently and neither is asked here;
# a value this side of it is the operator's call, bounded only by the engines.
MAX_TOKEN_VALUE = 2147483647

KIND_NUMBER = "number"
KIND_INTEGER = "integer"
KIND_STRINGS = "strings"


@dataclass(frozen=True)
class Field:
    """One knob: how it is stored, where it goes on the wire, how to render it.

    The bounds are the intersection of every engine in ``wire`` — a value the
    picker accepts must be accepted by all of them, because one stored set is
    applied to whichever model the conversation is on. Neither engine reports an
    out-of-range value back: llama.cpp clamps it, vLLM fails the request.

    ``wire`` maps an engine to the request key that engine was measured to take.
    A missing engine means do not send it and do not offer it.
    """

    name: str
    label: str
    kind: str
    minimum: Optional[float]
    maximum: Optional[float]
    wire: Mapping[str, str]
    step: Optional[float] = None
    exclusive_min: bool = False

    @property
    def engines(self) -> Tuple[str, ...]:
        return tuple(self.wire)

    def reject(self, value: Any) -> Optional[str]:
        """Rejection reason for one value, or None when it is acceptable."""
        if self.kind == KIND_STRINGS:
            return self._reject_strings(value)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"{self.name} must be a number"
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return f"{self.name} must be finite"
        if self.kind == KIND_INTEGER and not float(value).is_integer():
            return f"{self.name} must be an integer"
        if self.minimum is not None and (value < self.minimum
                                         or (self.exclusive_min and value == self.minimum)):
            bound = ">" if self.exclusive_min else ">="
            return f"{self.name} must be {bound} {self.minimum:g}"
        if self.maximum is not None and value > self.maximum:
            return f"{self.name} must be <= {self.maximum:g}"
        return None

    def _reject_strings(self, value: Any) -> Optional[str]:
        if not isinstance(value, list) or not value:
            return f"{self.name} must be a non-empty list of strings"
        if len(value) > MAX_STOP_ENTRIES:
            return f"{self.name} accepts at most {MAX_STOP_ENTRIES} entries"
        for entry in value:
            if not isinstance(entry, str) or not entry:
                return f"{self.name} entries must be non-empty strings"
            if len(entry) > MAX_STOP_CHARS:
                return f"{self.name} entries must be at most {MAX_STOP_CHARS} chars"
        return None


# Bounds are the engines', not llm-dock's taste: vLLM enforces them in
# SamplingParams.verify, llama.cpp declares them in its request schema, and where
# the two disagree the narrower one wins. `top_p` is excluded at 0 by vLLM's
# (0, 1]; `seed` stops at int32 because llama.cpp parses it as field_num.
FIELDS: Dict[str, Field] = {
    spec.name: spec
    for spec in (
        Field("temperature", "Temperature", KIND_NUMBER, 0.0, 2.0,
              {ENGINE_LLAMACPP: "temperature", ENGINE_VLLM: "temperature"}, step=0.1),
        Field("top_p", "Top-p", KIND_NUMBER, 0.0, 1.0,
              {ENGINE_LLAMACPP: "top_p", ENGINE_VLLM: "top_p"}, step=0.05,
              exclusive_min=True),
        Field("top_k", "Top-k", KIND_INTEGER, 0, MAX_TOKEN_VALUE,
              {ENGINE_LLAMACPP: "top_k", ENGINE_VLLM: "top_k"}),
        Field("min_p", "Min-p", KIND_NUMBER, 0.0, 1.0,
              {ENGINE_LLAMACPP: "min_p", ENGINE_VLLM: "min_p"}, step=0.05),
        Field("max_tokens", "Max tokens", KIND_INTEGER, 1, MAX_TOKEN_VALUE,
              {ENGINE_LLAMACPP: "max_tokens", ENGINE_VLLM: "max_tokens"}),
        # llama.cpp answers 200 and drops `repetition_penalty` on the floor; the
        # alias below is the only spelling that reaches its sampler.
        Field("repetition_penalty", "Repetition penalty", KIND_NUMBER, 0.0, 2.0,
              {ENGINE_LLAMACPP: "repeat_penalty",
               ENGINE_VLLM: "repetition_penalty"}, step=0.05, exclusive_min=True),
        Field("presence_penalty", "Presence penalty", KIND_NUMBER, -2.0, 2.0,
              {ENGINE_LLAMACPP: "presence_penalty",
               ENGINE_VLLM: "presence_penalty"}, step=0.1),
        Field("frequency_penalty", "Frequency penalty", KIND_NUMBER, -2.0, 2.0,
              {ENGINE_LLAMACPP: "frequency_penalty",
               ENGINE_VLLM: "frequency_penalty"}, step=0.1),
        Field("seed", "Seed", KIND_INTEGER, 0, MAX_TOKEN_VALUE,
              {ENGINE_LLAMACPP: "seed", ENGINE_VLLM: "seed"}),
        Field("stop", "Stop sequences", KIND_STRINGS, 1, MAX_STOP_ENTRIES,
              {ENGINE_LLAMACPP: "stop", ENGINE_VLLM: "stop"}),
    )
}

FIELD_ORDER: Tuple[str, ...] = tuple(FIELDS)

_GRAMMAR_HINT = (
    "expected an object with any of: " + ", ".join(FIELD_ORDER)
    + "; null or an empty object clears them"
)


def validate(raw: Any) -> Tuple[bool, List[str]]:
    """Strict field/type/range check for a write path: (is_valid, errors).

    Absent, null or empty is valid — that is how a conversation opts out or
    clears. Every violation is reported rather than just the first, so a client
    fixing one field does not meet a new error on the next save.
    """
    if raw is None or (isinstance(raw, dict) and not raw):
        return True, []
    if not isinstance(raw, dict):
        return False, [f"sampling_params must be an object or null; {_GRAMMAR_HINT}"]

    errors: List[str] = []
    for key in raw:
        if not isinstance(key, str) or key not in FIELDS:
            errors.append(f"sampling_params: unknown field {key!r}; {_GRAMMAR_HINT}")
    for name in FIELD_ORDER:
        if name in raw:
            reason = FIELDS[name].reject(raw[name])
            if reason:
                errors.append(f"sampling_params: {reason}")
    return (len(errors) == 0, errors)


def normalize(raw: Any) -> Optional[dict]:
    """Canonical form for storage: known fields only, in declaration order.

    None means "send nothing", and an empty object normalises to it so NULL is
    the column's only empty state. Never raises — callers validate first and use
    this after, or read back a stored blob through `from_storage`.
    """
    valid, _ = validate(raw)
    if not valid or not isinstance(raw, dict) or not raw:
        return None
    out: Dict[str, Any] = {}
    for name in FIELD_ORDER:
        if name in raw:
            value = raw[name]
            out[name] = int(value) if FIELDS[name].kind == KIND_INTEGER else value
    return out or None


def to_storage(raw: Any) -> Optional[str]:
    """The column value for a request-body value, or None to clear it."""
    normalized = normalize(raw)
    return None if normalized is None else json.dumps(normalized, separators=(",", ":"))


def from_storage(blob: Any) -> Optional[dict]:
    """A stored column back to a params dict, tolerant of junk."""
    if not isinstance(blob, str) or not blob:
        return None
    try:
        decoded = json.loads(blob)
    except ValueError:
        return None
    return normalize(decoded)


def supported_fields(engine: Optional[str],
                     capabilities: Optional[Sequence[str]] = None) -> List[Field]:
    """Fields to offer for one engine — the same list `request_fields` honours.

    `capabilities` only ever narrows the set (a per-model report of what upstream
    takes, for a host whose parameter support varies by model). A narrowing can
    remove a knob, never invent one, so a wrong capability list costs a control
    rather than a failing request.
    """
    if not engine:
        return []
    fields = [FIELDS[name] for name in FIELD_ORDER if engine in FIELDS[name].wire]
    if capabilities is None:
        return fields
    allowed = set(capabilities)
    return [field for field in fields if field.name in allowed]


def request_fields(params: Optional[Mapping[str, Any]], engine: Optional[str],
                   capabilities: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Request-body fields for stored params on one engine; ``{}`` changes nothing.

    Reads through `normalize` rather than trusting its argument, so a caller that
    skipped validation cannot put a value on the wire that the write path would
    have rejected. Fields the engine cannot take are left out, never renamed or
    substituted.
    """
    normalized = normalize(params)
    if not normalized:
        return {}
    offered = {field.name: field for field in supported_fields(engine, capabilities)}
    out: Dict[str, Any] = {}
    for name in FIELD_ORDER:
        field = offered.get(name)
        if name in normalized and field is not None:
            key = field.wire.get(engine or "")
            if key:
                out[key] = normalized[name]
    return out


def drop_unsupported(params: Optional[Mapping[str, Any]], engine: Optional[str],
                     capabilities: Optional[Sequence[str]] = None
                     ) -> Tuple[Optional[dict], List[str]]:
    """(applicable params, fields this engine cannot take) — what `run_started` reports.

    Returns the stored params unchanged rather than the wire dict: the report and
    the payload are built from one decision, and the caller needs the field names,
    not the engine's spelling of them.
    """
    normalized = normalize(params)
    if not normalized:
        return None, []
    offered = {field.name for field in supported_fields(engine, capabilities)}
    applicable = {name: value for name, value in normalized.items() if name in offered}
    dropped = [name for name in FIELD_ORDER
               if name in normalized and name not in offered]
    return (applicable or None, dropped)


def fields_descriptor(fields: Sequence[Field]) -> List[dict]:
    """Picker-facing descriptors: label, kind, bounds — so no client hardcodes them."""
    return [{
        "name": field.name,
        "label": field.label,
        "kind": field.kind,
        "min": field.minimum,
        "max": field.maximum,
        "step": field.step,
    } for field in fields]
