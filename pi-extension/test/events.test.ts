import { test } from "node:test";
import assert from "node:assert/strict";

import {
  EVENT_TYPES,
  EventStamper,
  gapEvent,
  isKnownEventType,
  stateBody,
  toolEndBody,
  userMessageBody,
} from "../src/events.ts";

test("event types are a typed set", () => {
  assert.ok(EVENT_TYPES.includes("state"));
  assert.ok(EVENT_TYPES.includes("assistant_message"));
  assert.equal(isKnownEventType("state"), true);
  assert.equal(isKnownEventType("unknown"), false);
});

test("stamper adds seq and ts to bodies", () => {
  const stamper = new EventStamper({ now: () => 1000 });
  assert.equal(stamper.current, 0);
  assert.deepEqual(stamper.stamp(stateBody("idle")), {
    type: "state", state: "idle", seq: 1, ts: 1000,
  });
  assert.deepEqual(stamper.stamp(userMessageBody("hi", 1, "extension")), {
    type: "user_message", text: "hi", image_count: 1, origin: "extension", seq: 2, ts: 1000,
  });
});

test("tool body uses wire field names", () => {
  const stamper = new EventStamper({ now: () => 1000 });
  assert.deepEqual(stamper.stamp(toolEndBody("call", "bash", "hi", false, 12, false)), {
    type: "tool_end", call_id: "call", name: "bash", result: "hi",
    is_error: false, duration_ms: 12, truncated: false, seq: 1, ts: 1000,
  });
});

test("gap event carries an explicit dropped seq", () => {
  assert.deepEqual(gapEvent(3, 1000, 3, 5), {
    type: "gap", seq: 3, ts: 1000, from_seq: 3, to_seq: 5,
  });
});
