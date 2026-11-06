import { test } from "node:test";
import assert from "node:assert/strict";

import {
  EventStamper,
  assistantDeltaBody,
  assistantMessageBody,
  stateBody,
  userMessageBody,
} from "../src/events.ts";
import { Outbox } from "../src/outbox.ts";

function makeStamper() {
  return new EventStamper({ now: () => 1000 });
}

test("overflow drops oldest deltas and records one gap", () => {
  const outbox = new Outbox(4, () => 1000);
  const stamper = makeStamper();
  outbox.enqueue(stamper.stamp(stateBody("idle")));
  outbox.enqueue(stamper.stamp(userMessageBody("hi", 0, "terminal")));
  outbox.enqueue(stamper.stamp(assistantDeltaBody("a", "")));
  outbox.enqueue(stamper.stamp(assistantMessageBody("final", "", null, null, "stop")));
  outbox.enqueue(stamper.stamp(assistantDeltaBody("b", "")));

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
  const stamper = makeStamper();
  outbox.enqueue(stamper.stamp(stateBody("idle")));
  outbox.enqueue(stamper.stamp(userMessageBody("hi", 0, "terminal")));
  outbox.enqueue(stamper.stamp(assistantMessageBody("final", "", null, null, "stop")));
  outbox.enqueue(stamper.stamp(assistantDeltaBody("delta", "")));
  const types = outbox.unacked().map((event) => event.type);
  assert.ok(types.includes("state"));
  assert.ok(types.includes("user_message"));
  assert.ok(types.includes("assistant_message"));
});

test("discard removes a batch and records a gap", () => {
  const outbox = new Outbox(10, () => 1000);
  const stamper = makeStamper();
  outbox.enqueue(stamper.stamp(stateBody("idle")));
  outbox.enqueue(stamper.stamp(assistantDeltaBody("a", "")));
  outbox.enqueue(stamper.stamp(assistantDeltaBody("b", "")));
  outbox.discard([2, 3]);
  const items = outbox.unacked();
  assert.deepEqual(items.map((event) => event.seq), [1, 2]);
  assert.equal(items[1].type, "gap");
  assert.equal(items[1].type === "gap" && items[1].from_seq, 2);
  assert.equal(items[1].type === "gap" && items[1].to_seq, 3);
});

test("ack removes everything up to the acknowledged seq", () => {
  const outbox = new Outbox(10, () => 1000);
  const stamper = makeStamper();
  outbox.enqueue(stamper.stamp(stateBody("idle")));
  outbox.enqueue(stamper.stamp(assistantDeltaBody("a", "")));
  outbox.enqueue(stamper.stamp(assistantDeltaBody("b", "")));
  outbox.ack(2);
  assert.deepEqual(outbox.unacked().map((event) => event.seq), [3]);
  outbox.ack(3);
  assert.equal(outbox.size, 0);
});
