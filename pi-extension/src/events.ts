import type { ModelRef } from "./protocol.ts";

export type EventOutcome = "completed" | "aborted" | "error";
export type MessageOrigin = "terminal" | "extension";
export type EventBase = { type: string; seq: number; ts: number };

export type StateEvent = EventBase & { type: "state"; state: "idle" | "working" };
export type UserMessageEvent = EventBase & {
  type: "user_message";
  text: string;
  image_count: number;
  origin: MessageOrigin;
};
export type AssistantDeltaEvent = EventBase & {
  type: "assistant_delta";
  text: string;
  thinking: string;
};

export type AssistantUsage = {
  input: number;
  output: number;
  cache_read: number;
  cache_write: number;
  reasoning: number | null;
  total_tokens: number;
  cost_total: number | null;
};
export type AssistantMessageEvent = EventBase & {
  type: "assistant_message";
  text: string;
  thinking: string;
  model: ModelRef | null;
  usage: AssistantUsage | null;
  stop_reason: string | null;
};
export type ToolStartEvent = EventBase & {
  type: "tool_start";
  call_id: string;
  name: string;
  args: string | null;
  truncated: boolean;
};
export type ToolUpdateEvent = EventBase & {
  type: "tool_update";
  call_id: string;
  name: string;
  partial: string | null;
  truncated: boolean;
};
export type ToolEndEvent = EventBase & {
  type: "tool_end";
  call_id: string;
  name: string;
  result: string | null;
  is_error: boolean;
  duration_ms: number | null;
  truncated: boolean;
};
export type TurnEndEvent = EventBase & { type: "turn_end"; outcome: EventOutcome };
export type RunEndEvent = EventBase & { type: "run_end"; outcome: EventOutcome };
export type ModelChangedEvent = EventBase & {
  type: "model_changed";
  model: ModelRef | null;
  previous: ModelRef | null;
};
export type ThinkingChangedEvent = EventBase & {
  type: "thinking_changed";
  level: string | null;
  previous: string | null;
};
export type CompactionEvent = EventBase & {
  type: "compaction";
  summary: string;
  tokens_before: number | null;
  reason: string;
};
export type GapEvent = EventBase & {
  type: "gap";
  from_seq: number;
  to_seq: number;
};

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
  | GapEvent;

export const EVENT_TYPES = new Set<string>([
  "state", "user_message", "assistant_delta", "assistant_message",
  "tool_start", "tool_update", "tool_end", "turn_end", "run_end",
  "model_changed", "thinking_changed", "compaction", "gap",
]);

export class EventSequencer {
  private seq = 0;
  next(): number {
    return (this.seq += 1);
  }
  get current(): number {
    return this.seq;
  }
}

export function stateEvent(seq: number, ts: number, state: "idle" | "working"): StateEvent {
  return { type: "state", seq, ts, state };
}
export function userMessageEvent(
  seq: number, ts: number, text: string, imageCount: number, origin: MessageOrigin,
): UserMessageEvent {
  return { type: "user_message", seq, ts, text, image_count: imageCount, origin };
}
export function assistantDeltaEvent(
  seq: number, ts: number, text: string, thinking: string,
): AssistantDeltaEvent {
  return { type: "assistant_delta", seq, ts, text, thinking };
}
export function assistantMessageEvent(
  seq: number, ts: number, text: string, thinking: string, model: ModelRef | null,
  usage: AssistantUsage | null, stopReason: string | null,
): AssistantMessageEvent {
  return { type: "assistant_message", seq, ts, text, thinking, model, usage, stop_reason: stopReason };
}
export function toolStartEvent(
  seq: number, ts: number, callId: string, name: string, args: string | null, truncated: boolean,
): ToolStartEvent {
  return { type: "tool_start", seq, ts, call_id: callId, name, args, truncated };
}
export function toolUpdateEvent(
  seq: number, ts: number, callId: string, name: string, partial: string | null, truncated: boolean,
): ToolUpdateEvent {
  return { type: "tool_update", seq, ts, call_id: callId, name, partial, truncated };
}
export function toolEndEvent(
  seq: number, ts: number, callId: string, name: string, result: string | null,
  isError: boolean, durationMs: number | null, truncated: boolean,
): ToolEndEvent {
  return { type: "tool_end", seq, ts, call_id: callId, name, result, is_error: isError, duration_ms: durationMs, truncated };
}
export function turnEndEvent(seq: number, ts: number, outcome: EventOutcome): TurnEndEvent {
  return { type: "turn_end", seq, ts, outcome };
}
export function runEndEvent(seq: number, ts: number, outcome: EventOutcome): RunEndEvent {
  return { type: "run_end", seq, ts, outcome };
}
export function modelChangedEvent(
  seq: number, ts: number, model: ModelRef | null, previous: ModelRef | null,
): ModelChangedEvent {
  return { type: "model_changed", seq, ts, model, previous };
}
export function thinkingChangedEvent(
  seq: number, ts: number, level: string | null, previous: string | null,
): ThinkingChangedEvent {
  return { type: "thinking_changed", seq, ts, level, previous };
}
export function compactionEvent(
  seq: number, ts: number, summary: string, tokensBefore: number | null, reason: string,
): CompactionEvent {
  return { type: "compaction", seq, ts, summary, tokens_before: tokensBefore, reason };
}
export function gapEvent(seq: number, ts: number, fromSeq: number, toSeq: number): GapEvent {
  return { type: "gap", seq, ts, from_seq: fromSeq, to_seq: toSeq };
}
