import { test } from "node:test";
import assert from "node:assert/strict";

import { EVENT_TYPES, EventStamper, isKnownEventType } from "../src/events.ts";
import { promptClosedBody, promptOpenBody } from "../src/prompt-events.ts";
import type { PromptSpec } from "../src/prompt-book.ts";

const spec: PromptSpec = {
  prompt_id: "call-1",
  kind: "select",
  title: "Pick a port",
  message: "Which port should the service use",
  options: ["3301", "3302"],
  allow_free_text: true,
  timeout_ms: 30000,
};

test("prompt event types are known and listed", () => {
  assert.ok(EVENT_TYPES.includes("prompt_open"));
  assert.ok(EVENT_TYPES.includes("prompt_closed"));
  assert.equal(isKnownEventType("prompt_open"), true);
  assert.equal(isKnownEventType("prompt_closed"), true);
  assert.equal(EVENT_TYPES.length, 15);
});

test("prompt_open body carries the whole spec", () => {
  assert.deepEqual(promptOpenBody(spec), {
    type: "prompt_open",
    prompt_id: "call-1",
    kind: "select",
    title: "Pick a port",
    message: "Which port should the service use",
    options: ["3301", "3302"],
    allow_free_text: true,
    timeout_ms: 30000,
  });
});

test("prompt_open copies the options array", () => {
  const body = promptOpenBody(spec);
  body.options.push("3303");
  assert.deepEqual(spec.options, ["3301", "3302"]);
});

test("prompt_closed body carries reason, value and source", () => {
  assert.deepEqual(promptClosedBody("call-1", "answered", "3302", "remote"), {
    type: "prompt_closed",
    prompt_id: "call-1",
    reason: "answered",
    value: "3302",
    answered_by: "remote",
  });
  assert.deepEqual(promptClosedBody("call-1", "expired", null, null), {
    type: "prompt_closed",
    prompt_id: "call-1",
    reason: "expired",
    value: null,
    answered_by: null,
  });
});

test("the stamper sequences prompt events like any other", () => {
  let now = 1000;
  const stamper = new EventStamper({ now: () => now });
  const open = stamper.stamp(promptOpenBody(spec));
  now = 1500;
  const closed = stamper.stamp(promptClosedBody("call-1", "answered", true, "terminal"));
  assert.deepEqual(
    { seq: open.seq, ts: open.ts, type: open.type, prompt_id: open.prompt_id },
    { seq: 1, ts: 1000, type: "prompt_open", prompt_id: "call-1" },
  );
  assert.deepEqual(
    { seq: closed.seq, ts: closed.ts, type: closed.type, answered_by: closed.answered_by },
    { seq: 2, ts: 1500, type: "prompt_closed", answered_by: "terminal" },
  );
});
