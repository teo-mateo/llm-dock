import { test } from "node:test";
import assert from "node:assert/strict";

import { assistantMessageEvent, assistantDeltaEvent, stateEvent, userMessageEvent } from "../src/events.ts";
import { Outbox } from "../src/outbox.ts";

const assistantMessage = assistantMessageEvent(4, 1000, "final", "", null, null, "stop");

test("overflow drops oldest deltas and records one gap", () => {
  const outbox = new Outbox(4, () => 1000);
  outbox.enqueue(stateEvent(1, 1000, "idle"));
  outbox.enqueue(userMessageEvent(2, 1000, "hi", 0, "terminal"));
  outbox.enqueue(assistantDeltaEvent(3, 1000, "a", ""));
  outbox.enqueue(assistantMessage);
  outbox.enqueue(assistantDeltaEvent(5, 1000, "b", ""));

  const items = outbox.unacked();
  assert.deepEqual(items.map((event) => event.seq), [1, 2, 3, 4, 5]);
  assert.deepEqual(items.map((event) => event.type), [
    "state", "user_message", "gap", "assistant_message", "assistant_delta",
  ]);
  const gap = items.find((event) => event.type === "gap");
  assert.ok(gap && gap.type === "gap");
  assert.deepEqual({ from: gap.from_seq, to: gap.to_seq }, { from: 3, to: 3 });
  assert.equal(outbox.dataSize, 4);
  assert.equal(outbox.size, 5);
});

test("protected events are never dropped", () => {
  const outbox = new Outbox(3, () => 1000);
  outbox.enqueue(stateEvent(1, 1000, "idle"));
  outbox.enqueue(userMessageEvent(2, 1000, "hi", 0, "terminal"));
  outbox.enqueue(assistantMessage);
  outbox.enqueue(assistantDeltaEvent(4, 1000, "delta", ""));
  const types = outbox.unacked().map((event) => event.type);
  assert.ok(types.includes("state"));
  assert.ok(types.includes("user_message"));
  assert.ok(types.includes("assistant_message"));
});

test("ack removes everything up to the acknowledged seq", () => {
  const outbox = new Outbox(10, () => 1000);
  outbox.enqueue(stateEvent(1, 1000, "idle"));
  outbox.enqueue(assistantDeltaEvent(2, 1000, "a", ""));
  outbox.enqueue(assistantDeltaEvent(3, 1000, "b", ""));
  outbox.ack(2);
  assert.deepEqual(outbox.unacked().map((event) => event.seq), [3]);
  outbox.ack(3);
  assert.equal(outbox.size, 0);
});
