import { test } from "node:test";
import assert from "node:assert/strict";

import { EventStamper } from "../src/events.ts";
import { createAnswerPromptHandler, RemotePrompts } from "../src/remote-prompts.ts";
import type { PromptSpec, PromptValue } from "../src/prompt-book.ts";
import { fakeClock, flush } from "./fake-clock.ts";

type Emitted = Record<string, unknown>;

function harness(timeoutMs: number | null = null) {
  const clock = fakeClock(0);
  const emitted: Emitted[] = [];
  const stamper = new EventStamper(clock);
  const prompts = new RemotePrompts({
    stamper,
    emit: (event) => emitted.push(event as unknown as Emitted),
    clock,
  });
  const spec = (overrides: Partial<PromptSpec> = {}): PromptSpec => ({
    prompt_id: "call-1",
    kind: "input",
    title: "Which one",
    message: "",
    options: [],
    allow_free_text: false,
    timeout_ms: timeoutMs,
    ...overrides,
  });
  return { clock, emitted, prompts, spec, types: () => emitted.map((event) => event.type) };
}

test("open emits a stamped prompt_open", () => {
  const { prompts, emitted, spec } = harness();
  prompts.open(spec());
  assert.deepEqual(emitted, [{
    type: "prompt_open",
    prompt_id: "call-1",
    kind: "input",
    title: "Which one",
    message: "",
    options: [],
    allow_free_text: false,
    timeout_ms: null,
    seq: 1,
    ts: 0,
  }]);
});

test("a remote answer resolves the waiter and emits prompt_closed", async () => {
  const { prompts, emitted, spec, types } = harness();
  prompts.open(spec());
  const waiting = prompts.waitFor("call-1");
  assert.equal(prompts.answerRemote("call-1", "3301"), "answered");
  assert.deepEqual(await waiting, { value: "3301", source: "remote" });
  assert.deepEqual(types(), ["prompt_open", "prompt_closed"]);
  assert.deepEqual(emitted[1], {
    type: "prompt_closed",
    prompt_id: "call-1",
    reason: "answered",
    value: "3301",
    answered_by: "remote",
    seq: 2,
    ts: 0,
  });
});

test("a terminal answer is attributed to the terminal", () => {
  const { prompts, emitted, spec, types } = harness();
  prompts.open(spec({ kind: "confirm" }));
  assert.equal(prompts.answerTerminal("call-1", true), "answered");
  assert.deepEqual(types(), ["prompt_open", "prompt_closed"]);
  assert.equal(emitted[1].answered_by, "terminal");
  assert.equal(emitted[1].value, true);
});

test("a repeat answer reports already_answered and emits nothing", () => {
  const { prompts, emitted, spec, types } = harness();
  prompts.open(spec());
  prompts.answerRemote("call-1", "x");
  assert.equal(prompts.answerRemote("call-1", "y"), "already_answered");
  assert.equal(prompts.answerTerminal("call-1", "z"), "already_answered");
  assert.deepEqual(types(), ["prompt_open", "prompt_closed"]);
  assert.equal(emitted.length, 2);
});

test("unknown prompts and invalid values emit nothing", () => {
  const { prompts, spec, types } = harness();
  assert.equal(prompts.answerRemote("nope", "x"), "unknown");
  prompts.open(spec({ kind: "confirm" }));
  assert.equal(prompts.answerRemote("call-1", "yes"), "invalid_value");
  assert.deepEqual(types(), ["prompt_open"]);
});

test("cancel and expire emit their reasons once", () => {
  const { prompts, emitted, spec, types } = harness();
  prompts.open(spec({ prompt_id: "a" }));
  prompts.open(spec({ prompt_id: "b" }));
  assert.equal(prompts.cancel("a"), true);
  assert.equal(prompts.cancel("a"), false);
  assert.equal(prompts.expire("b"), true);
  assert.equal(prompts.expire("b"), false);
  assert.deepEqual(types(), ["prompt_open", "prompt_open", "prompt_closed", "prompt_closed"]);
  assert.deepEqual(
    emitted.slice(2).map((event) => [event.prompt_id, event.reason, event.value, event.answered_by]),
    [["a", "cancelled", null, null], ["b", "expired", null, null]],
  );
});

test("timeout_ms expires the prompt through the injected clock", async () => {
  const { prompts, clock, spec, types } = harness(5000);
  prompts.open(spec());
  const waiting = prompts.waitFor("call-1");
  await clock.advance(5000);
  await flush();
  assert.equal(await waiting, null);
  assert.equal(prompts.status("call-1"), "expired");
  assert.deepEqual(types(), ["prompt_open", "prompt_closed"]);
});

test("answering clears the expiry timer", async () => {
  const { prompts, clock, spec, types } = harness(5000);
  prompts.open(spec());
  prompts.answerRemote("call-1", "x");
  await clock.advance(5000);
  assert.deepEqual(types(), ["prompt_open", "prompt_closed"]);
  assert.equal(clock.pending().length, 0);
});

test("replayOpen re-emits exactly the open set", () => {
  const { prompts, emitted, spec, types } = harness();
  prompts.open(spec({ prompt_id: "a" }));
  prompts.open(spec({ prompt_id: "b" }));
  prompts.answerRemote("a", "x");
  emitted.length = 0;
  prompts.replayOpen();
  assert.deepEqual(types(), ["prompt_open"]);
  assert.equal(emitted[0].prompt_id, "b");
  assert.equal(emitted[0].seq, 4);
});

test("replayOpen is silent when nothing is open", () => {
  const { prompts, spec, types } = harness();
  prompts.open(spec());
  prompts.cancel("call-1");
  const before = types().length;
  prompts.replayOpen();
  assert.equal(types().length, before);
});

test("answer_prompt handler maps outcomes to command results", () => {
  const { prompts, spec } = harness();
  const handler = createAnswerPromptHandler(prompts);
  prompts.open(spec({ kind: "select", options: ["a", "b"] }));
  prompts.open(spec({ prompt_id: "other", kind: "select", options: ["a", "b"] }));
  const value: PromptValue = "a";
  assert.deepEqual(handler({ prompt_id: "call-1", value }, "c1"), {
    command_id: "c1", ok: true, error: null,
  });
  assert.deepEqual(handler({ prompt_id: "call-1", value: "b" }, "c2"), {
    command_id: "c2", ok: false, error: "prompt_already_answered",
  });
  assert.deepEqual(handler({ prompt_id: "gone", value: "a" }, "c3"), {
    command_id: "c3", ok: false, error: "prompt_unknown",
  });
  assert.deepEqual(handler({ prompt_id: "other", value: 7 }, "c4"), {
    command_id: "c4", ok: false, error: "invalid_value",
  });
  assert.deepEqual(handler({ value: "a" }, "c5"), {
    command_id: "c5", ok: false, error: "invalid_args",
  });
});
