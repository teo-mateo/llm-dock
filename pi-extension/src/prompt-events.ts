import type { PromptKind, PromptSource, PromptSpec, PromptValue } from "./prompt-book.ts";
import type { EventBase } from "./events.ts";

export type PromptCloseReason = "answered" | "cancelled" | "expired";

export type PromptOpenBody = {
  type: "prompt_open";
  prompt_id: string;
  kind: PromptKind;
  title: string;
  message: string;
  options: string[];
  allow_free_text: boolean;
  timeout_ms: number | null;
};

export type PromptClosedBody = {
  type: "prompt_closed";
  prompt_id: string;
  reason: PromptCloseReason;
  value: PromptValue | null;
  answered_by: PromptSource | null;
};

export type PromptOpenEvent = EventBase & PromptOpenBody;
export type PromptClosedEvent = EventBase & PromptClosedBody;

export function promptOpenBody(spec: PromptSpec): PromptOpenBody {
  return {
    type: "prompt_open",
    prompt_id: spec.prompt_id,
    kind: spec.kind,
    title: spec.title,
    message: spec.message,
    options: [...spec.options],
    allow_free_text: spec.allow_free_text,
    timeout_ms: spec.timeout_ms,
  };
}

export function promptClosedBody(
  promptId: string,
  reason: PromptCloseReason,
  value: PromptValue | null,
  answeredBy: PromptSource | null,
): PromptClosedBody {
  return {
    type: "prompt_closed",
    prompt_id: promptId,
    reason,
    value,
    answered_by: answeredBy,
  };
}
