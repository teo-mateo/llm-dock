import type { PromptClosedBody, PromptClosedEvent, PromptOpenBody, PromptOpenEvent } from "./prompt-events.ts";
import type { ModelRef } from "./protocol.ts";

export type EventOutcome = "completed" | "aborted" | "error";
export type MessageOrigin = "terminal" | "extension";

export const EVENT_TYPES = [
  "state",
  "user_message",
  "assistant_delta",
  "assistant_message",
  "tool_start",
  "tool_update",
  "tool_end",
  "turn_end",
  "run_end",
  "model_changed",
  "thinking_changed",
  "compaction",
  "gap",
  "prompt_open",
  "prompt_closed",
] as const;

export type EventType = (typeof EVENT_TYPES)[number];
export type EventBase = { type: EventType; seq: number; ts: number };

export type StateEvent = EventBase & { type: "state"; state: "idle" | "working" };
export type UserMessageEvent = EventBase & {
  type: "user_message"; text: string; image_count: number; origin: MessageOrigin;
};
export type AssistantDeltaEvent = EventBase & {
  type: "assistant_delta"; text: string; thinking: string;
};
export type AssistantUsage = {
  input: number; output: number; cache_read: number; cache_write: number;
  reasoning: number | null; total_tokens: number; cost_total: number | null;
};
export type AssistantMessageEvent = EventBase & {
  type: "assistant_message"; text: string; thinking: string;
  model: ModelRef | null; usage: AssistantUsage | null; stop_reason: string | null;
};
export type ToolStartEvent = EventBase & {
  type: "tool_start"; call_id: string; name: string; args: string | null; truncated: boolean;
};
export type ToolUpdateEvent = EventBase & {
  type: "tool_update"; call_id: string; name: string; partial: string | null; truncated: boolean;
};
export type ToolEndEvent = EventBase & {
  type: "tool_end"; call_id: string; name: string; result: string | null;
  is_error: boolean; duration_ms: number | null; truncated: boolean;
};
export type TurnEndEvent = EventBase & { type: "turn_end"; outcome: EventOutcome };
export type RunEndEvent = EventBase & { type: "run_end"; outcome: EventOutcome };
export type ModelChangedEvent = EventBase & {
  type: "model_changed"; model: ModelRef | null; previous: ModelRef | null;
};
export type ThinkingChangedEvent = EventBase & {
  type: "thinking_changed"; level: string | null; previous: string | null;
};
export type CompactionEvent = EventBase & {
  type: "compaction"; summary: string; tokens_before: number | null; reason: string;
};
export type GapEvent = EventBase & { type: "gap"; from_seq: number; to_seq: number };

export type WireEvent =
  | StateEvent
  | UserMessageEvent
  | AssistantDeltaEvent
  | AssistantMessageEvent
  | ToolStartEvent
  | ToolUpdateEvent
  | ToolEndEvent
  | TurnEndEvent
  | RunEndEvent
  | ModelChangedEvent
  | ThinkingChangedEvent
  | CompactionEvent
  | GapEvent
  | PromptOpenEvent
  | PromptClosedEvent;

export type StateBody = Omit<StateEvent, "seq" | "ts">;
export type UserMessageBody = Omit<UserMessageEvent, "seq" | "ts">;
export type AssistantDeltaBody = Omit<AssistantDeltaEvent, "seq" | "ts">;
export type AssistantMessageBody = Omit<AssistantMessageEvent, "seq" | "ts">;
export type ToolStartBody = Omit<ToolStartEvent, "seq" | "ts">;
export type ToolUpdateBody = Omit<ToolUpdateEvent, "seq" | "ts">;
export type ToolEndBody = Omit<ToolEndEvent, "seq" | "ts">;
export type TurnEndBody = Omit<TurnEndEvent, "seq" | "ts">;
export type RunEndBody = Omit<RunEndEvent, "seq" | "ts">;
export type ModelChangedBody = Omit<ModelChangedEvent, "seq" | "ts">;
export type ThinkingChangedBody = Omit<ThinkingChangedEvent, "seq" | "ts">;
export type CompactionBody = Omit<CompactionEvent, "seq" | "ts">;

export type EventBody =
  | StateBody
  | UserMessageBody
  | AssistantDeltaBody
  | AssistantMessageBody
  | ToolStartBody
  | ToolUpdateBody
  | ToolEndBody
  | TurnEndBody
  | RunEndBody
  | ModelChangedBody
  | ThinkingChangedBody
  | CompactionBody
  | PromptOpenBody
  | PromptClosedBody;

export type StamperClock = { now: () => number };

export class EventStamper {
  private seq = 0;
  private readonly clock: StamperClock;

  constructor(clock: StamperClock) {
    this.clock = clock;
  }

  now(): number {
    return this.clock.now();
  }

  stamp<T extends EventBody>(body: T): T & { seq: number; ts: number } {
    this.seq += 1;
    return { ...body, seq: this.seq, ts: this.clock.now() };
  }

  get current(): number {
    return this.seq;
  }
}

export function isKnownEventType(type: string): type is EventType {
  return (EVENT_TYPES as readonly string[]).includes(type);
}

export function stateBody(state: "idle" | "working"): StateBody {
  return { type: "state", state };
}
export function userMessageBody(
  text: string, imageCount: number, origin: MessageOrigin,
): UserMessageBody {
  return { type: "user_message", text, image_count: imageCount, origin };
}
export function assistantDeltaBody(text: string, thinking: string): AssistantDeltaBody {
  return { type: "assistant_delta", text, thinking };
}
export function assistantMessageBody(
  text: string, thinking: string, model: ModelRef | null,
  usage: AssistantUsage | null, stopReason: string | null,
): AssistantMessageBody {
  return { type: "assistant_message", text, thinking, model, usage, stop_reason: stopReason };
}
export function toolStartBody(
  callId: string, name: string, args: string | null, truncated: boolean,
): ToolStartBody {
  return { type: "tool_start", call_id: callId, name, args, truncated };
}
export function toolUpdateBody(
  callId: string, name: string, partial: string | null, truncated: boolean,
): ToolUpdateBody {
  return { type: "tool_update", call_id: callId, name, partial, truncated };
}
export function toolEndBody(
  callId: string, name: string, result: string | null, isError: boolean,
  durationMs: number | null, truncated: boolean,
): ToolEndBody {
  return {
    type: "tool_end", call_id: callId, name, result,
    is_error: isError, duration_ms: durationMs, truncated,
  };
}
export function turnEndBody(outcome: EventOutcome): TurnEndBody {
  return { type: "turn_end", outcome };
}
export function runEndBody(outcome: EventOutcome): RunEndBody {
  return { type: "run_end", outcome };
}
export function modelChangedBody(model: ModelRef | null, previous: ModelRef | null): ModelChangedBody {
  return { type: "model_changed", model, previous };
}
export function thinkingChangedBody(level: string | null, previous: string | null): ThinkingChangedBody {
  return { type: "thinking_changed", level, previous };
}
export function compactionBody(summary: string, tokensBefore: number | null, reason: string): CompactionBody {
  return { type: "compaction", summary, tokens_before: tokensBefore, reason };
}
export function gapEvent(seq: number, ts: number, fromSeq: number, toSeq: number): GapEvent {
  return { type: "gap", seq, ts, from_seq: fromSeq, to_seq: toSeq };
}
