import { isKnownEventType, type EventType } from "../src/events.ts";
import { MAX_EVENTS_BATCH, MAX_EVENTS_BODY_BYTES } from "../src/protocol.ts";

export type StoredEvent = {
  type: string;
  seq: number;
  ts: number;
  [key: string]: unknown;
};

export type EventStore = Map<string, Map<number, StoredEvent>>;

function isInt(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

function isNullableString(value: unknown): boolean {
  return value === null || typeof value === "string";
}

function isModelRef(value: unknown): boolean {
  if (!value || typeof value !== "object") return false;
  const ref = value as { provider?: unknown; id?: unknown };
  return typeof ref.provider === "string" && typeof ref.id === "string";
}

function isNullableModelRef(value: unknown): boolean {
  return value === null || isModelRef(value);
}

function isNullableNumber(value: unknown): boolean {
  return value === null || typeof value === "number";
}

function isUsage(value: unknown): boolean {
  if (!value || typeof value !== "object") return false;
  const usage = value as Record<string, unknown>;
  for (const key of ["input", "output", "cache_read", "cache_write", "total_tokens"]) {
    if (typeof usage[key] !== "number") return false;
  }
  return isNullableNumber(usage.reasoning) && isNullableNumber(usage.cost_total);
}

function isNullableUsage(value: unknown): boolean {
  return value === null || isUsage(value);
}

function isOutcome(value: unknown): boolean {
  return value === "completed" || value === "aborted" || value === "error";
}

export function validEvent(event: unknown): boolean {
  if (!event || typeof event !== "object" || Array.isArray(event)) return false;
  const typed = event as Record<string, unknown>;
  const type = typed.type;
  if (typeof type !== "string" || !isInt(typed.seq) || typed.seq < 1) return false;
  if (!isInt(typed.ts) || typed.ts < 0) return false;

  if (!isKnownEventType(type)) return true;

  switch (type as EventType) {
    case "gap":
      return isInt(typed.from_seq) && isInt(typed.to_seq)
        && typed.from_seq >= 1 && typed.to_seq >= typed.from_seq;
    case "state":
      return typed.state === "idle" || typed.state === "working";
    case "user_message":
      return typeof typed.text === "string"
        && isInt(typed.image_count) && typed.image_count >= 0
        && (typed.origin === "terminal" || typed.origin === "extension");
    case "assistant_delta":
      return typeof typed.text === "string" && typeof typed.thinking === "string";
    case "assistant_message":
      return typeof typed.text === "string" && typeof typed.thinking === "string"
        && isNullableModelRef(typed.model)
        && isNullableUsage(typed.usage)
        && isNullableString(typed.stop_reason);
    case "tool_start":
      return typeof typed.call_id === "string" && typeof typed.name === "string"
        && isNullableString(typed.args) && typeof typed.truncated === "boolean";
    case "tool_update":
      return typeof typed.call_id === "string" && typeof typed.name === "string"
        && isNullableString(typed.partial) && typeof typed.truncated === "boolean";
    case "tool_end":
      return typeof typed.call_id === "string" && typeof typed.name === "string"
        && isNullableString(typed.result)
        && typeof typed.is_error === "boolean"
        && isNullableNumber(typed.duration_ms)
        && typeof typed.truncated === "boolean";
    case "turn_end":
    case "run_end":
      return isOutcome(typed.outcome);
    case "model_changed":
      return isNullableModelRef(typed.model) && isNullableModelRef(typed.previous);
    case "thinking_changed":
      return isNullableString(typed.level) && isNullableString(typed.previous);
    case "compaction":
      return typeof typed.summary === "string"
        && isNullableNumber(typed.tokens_before)
        && typeof typed.reason === "string";
  }
  return true;
}

export function ackedSeq(stored: Map<number, StoredEvent>): number {
  if (stored.size === 0) return 0;
  const first = Math.min(...stored.keys());
  const covered = new Set<number>();
  for (const [seq, event] of stored) {
    covered.add(seq);
    if (event.type === "gap") {
      const from = event.from_seq as number;
      const to = event.to_seq as number;
      for (let s = from; s <= to; s += 1) covered.add(s);
    }
  }
  let acked = first - 1;
  while (covered.has(acked + 1)) acked += 1;
  return acked;
}

export function handleEvents(
  frame: Record<string, unknown>,
  stored: Map<number, StoredEvent>,
): { status: number; payload: unknown } {
  const events = frame.events;
  if (!Array.isArray(events) || events.length > MAX_EVENTS_BATCH) {
    return { status: 400, payload: { ok: false, protocol: 1, error: "bad_frame" } };
  }
  if (Buffer.byteLength(JSON.stringify(frame)) > MAX_EVENTS_BODY_BYTES) {
    return { status: 400, payload: { ok: false, protocol: 1, error: "bad_frame" } };
  }
  if (!events.every(validEvent)) {
    return { status: 400, payload: { ok: false, protocol: 1, error: "bad_frame" } };
  }
  for (const event of events as StoredEvent[]) {
    if (!stored.has(event.seq)) stored.set(event.seq, event);
  }
  return {
    status: 200,
    payload: { ok: true, protocol: 1, acked_seq: ackedSeq(stored) },
  };
}


export type OpenPrompt = {
  key: string;
  seq: number;
  promptId: string;
  kind: string;
  options: string[];
};

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item) => typeof item === "string") : [];
}

export function openPrompts(events: EventStore): OpenPrompt[] {
  const open = new Map<string, OpenPrompt>();
  for (const [key, stored] of events) {
    for (const seq of [...stored.keys()].sort((a, b) => a - b)) {
      const event = stored.get(seq);
      if (!event || (event.type !== "prompt_open" && event.type !== "prompt_closed")) continue;
      const promptId = String(event.prompt_id ?? "");
      if (!promptId) continue;
      const id = `${key}|${promptId}`;
      if (event.type === "prompt_closed") {
        open.delete(id);
        continue;
      }
      open.set(id, {
        key,
        seq,
        promptId,
        kind: String(event.kind ?? "input"),
        options: strings(event.options),
      });
    }
  }
  return [...open.values()].sort((a, b) => a.seq - b.seq);
}

export function answerForPrompt(prompt: OpenPrompt): unknown {
  if (prompt.kind === "confirm") return true;
  if (prompt.kind === "select") return prompt.options[0] ?? null;
  return "from phone";
}
