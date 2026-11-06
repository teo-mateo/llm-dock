import { test } from "node:test";
import assert from "node:assert/strict";

import {
  EVENT_TYPES,
  EventSequencer,
  assistantMessageEvent,
  gapEvent,
  stateEvent,
  toolEndEvent,
  userMessageEvent,
} from "../src/events.ts";

test("sequencer starts at 1 and increments", () => {
  const sequencer = new EventSequencer();
  assert.equal(sequencer.current, 0);
  assert.equal(sequencer.next(), 1);
  assert.equal(sequencer.next(), 2);
  assert.equal(sequencer.current, 2);
});

test("event types are known", () => {
  assert.ok(EVENT_TYPES.has("state"));
  assert.ok(EVENT_TYPES.has("assistant_message"));
  assert.equal(EVENT_TYPES.has("unknown"), false);
});

test("builders use the wire field names", () => {
  assert.deepEqual(stateEvent(1, 1000, "idle"), {
    type: "state", seq: 1, ts: 1000, state: "idle",
  });
  assert.deepEqual(userMessageEvent(2, 1000, "hi", 1, "extension"), {
    type: "user_message", seq: 2, ts: 1000, text: "hi", image_count: 1, origin: "extension",
  });
  assert.deepEqual(gapEvent(3, 1000, 3, 5), {
    type: "gap", seq: 3, ts: 1000, from_seq: 3, to_seq: 5,
  });
  assert.deepEqual(toolEndEvent(4, 1000, "call", "bash", "hi", false, 12, false), {
    type: "tool_end", seq: 4, ts: 1000, call_id: "call", name: "bash",
    result: "hi", is_error: false, duration_ms: 12, truncated: false,
  });
});

test("assistant message carries usage and stop reason", () => {
  const event = assistantMessageEvent(
    1, 1000, "text", "thinking", { provider: "mistral", id: "small" },
    { input: 5, output: 3, cache_read: 0, cache_write: 0, reasoning: null, total_tokens: 8, cost_total: 0 },
    "stop",
  );
  assert.equal(event.model?.provider, "mistral");
  assert.equal(event.stop_reason, "stop");
  assert.equal(event.usage?.total_tokens, 8);
});
