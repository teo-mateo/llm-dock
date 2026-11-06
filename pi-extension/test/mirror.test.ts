import { test } from "node:test";
import assert from "node:assert/strict";

import { createActivity } from "../src/activity.ts";
import { EventStamper, type WireEvent } from "../src/events.ts";
import { EventMirror } from "../src/mirror.ts";
import { fakeClock } from "./fake-clock.ts";

function makeMirror() {
  const clock = fakeClock(1000);
  const emitted: WireEvent[] = [];
  const activity = createActivity();
  const stamper = new EventStamper(clock);
  const mirror = new EventMirror({
    stamper,
    activity,
    emit: (event) => emitted.push(event),
  });
  return { clock, emitted, mirror, activity };
}

test("input, agent state, deltas and the final assistant message", async () => {
  const { clock, emitted, mirror, activity } = makeMirror();

  mirror.handle({
    type: "input",
    text: "say hi",
    images: [{ type: "image", data: "", mimeType: "image/png" }],
    source: "interactive",
  } as any);
  mirror.handle({ type: "agent_start" } as any);

  mirror.handle({
    type: "message_update",
    assistantMessageEvent: { type: "text_delta", delta: "hel", contentIndex: 0, partial: {} },
  } as any);
  await clock.advance(50);
  mirror.handle({
    type: "message_update",
    assistantMessageEvent: { type: "thinking_delta", delta: "th", contentIndex: 0, partial: {} },
  } as any);
  await clock.advance(50);
  mirror.handle({
    type: "message_update",
    assistantMessageEvent: { type: "text_delta", delta: "lo", contentIndex: 0, partial: {} },
  } as any);

  mirror.handle({
    type: "message_end",
    message: {
      role: "assistant",
      content: [
        { type: "text", text: "hello" },
        { type: "thinking", thinking: "think" },
      ],
      provider: "mistral",
      model: "small",
      usage: {
        input: 5,
        output: 3,
        cacheRead: 1,
        cacheWrite: 0,
        reasoning: 2,
        totalTokens: 9,
        cost: { total: 0.01 },
      },
      stopReason: "stop",
    },
  } as any);

  assert.deepEqual(emitted.map((event) => event.type), [
    "user_message", "state", "assistant_delta", "assistant_delta", "assistant_message",
  ]);
  assert.equal(emitted[0].type === "user_message" && emitted[0].origin, "terminal");
  assert.equal(activity.working, true);
  assert.equal(emitted[0].type === "user_message" && emitted[0].image_count, 1);
  assert.equal(emitted[2].type === "assistant_delta" && emitted[2].text, "hel");
  assert.equal(emitted[2].type === "assistant_delta" && emitted[2].thinking, "th");
  assert.equal(emitted[3].type === "assistant_delta" && emitted[3].text, "lo");
  assert.equal(emitted[4].type === "assistant_message" && emitted[4].text, "hello");
  assert.equal(emitted[4].type === "assistant_message" && emitted[4].thinking, "think");
  assert.equal(emitted[4].type === "assistant_message" && emitted[4].model?.id, "small");
  assert.equal(emitted[4].type === "assistant_message" && emitted[4].stop_reason, "stop");
});

test("tool events are throttled and ended", async () => {
  const { clock, emitted, mirror } = makeMirror();

  mirror.handle({
    type: "tool_execution_start",
    toolCallId: "call-1",
    toolName: "bash",
    args: { command: "echo hi" },
  } as any);
  mirror.handle({
    type: "tool_execution_update",
    toolCallId: "call-1",
    toolName: "bash",
    args: { command: "echo hi" },
    partialResult: "line",
  } as any);
  await clock.advance(100);
  mirror.handle({
    type: "tool_execution_update",
    toolCallId: "call-1",
    toolName: "bash",
    args: { command: "echo hi" },
    partialResult: "line",
  } as any);
  await clock.advance(150);
  mirror.handle({
    type: "tool_execution_update",
    toolCallId: "call-1",
    toolName: "bash",
    args: { command: "echo hi" },
    partialResult: "line two",
  } as any);
  mirror.handle({
    type: "tool_execution_end",
    toolCallId: "call-1",
    toolName: "bash",
    result: { output: "hi" },
    isError: false,
    durationMs: 12,
  } as any);

  assert.deepEqual(emitted.map((event) => event.type), [
    "tool_start", "tool_update", "tool_update", "tool_end",
  ]);
  assert.equal(emitted[0].type === "tool_start" && emitted[0].call_id, "call-1");
  assert.equal(emitted[0].type === "tool_start" && emitted[0].args, '{"command":"echo hi"}');
  assert.equal(emitted[1].type === "tool_update" && emitted[1].partial, "line");
  assert.equal(emitted[2].type === "tool_update" && emitted[2].partial, "line two");
  assert.equal(emitted[3].type === "tool_end" && emitted[3].result, '{"output":"hi"}');
  assert.equal(emitted[3].type === "tool_end" && emitted[3].duration_ms, 12);
});

test("run end, turn end, model, thinking and compaction", () => {
  const { emitted, mirror, activity } = makeMirror();

  mirror.handle({ type: "agent_start" } as any);
  mirror.handle({ type: "agent_before_settle", outcome: "error" } as any);
  mirror.handle({ type: "agent_settled" } as any);
  mirror.handle({ type: "turn_end", outcome: "completed" } as any);
  mirror.handle({
    type: "model_select",
    model: { provider: "mistral", id: "small" },
    previousModel: { provider: "mistral", id: "tiny" },
  } as any);
  mirror.handle({
    type: "thinking_level_select",
    level: "high",
    previousLevel: "low",
  } as any);
  mirror.handle({
    type: "session_compact",
    compactionEntry: { summary: "sum", tokensBefore: 100 },
    reason: "manual",
  } as any);

  assert.deepEqual(emitted.map((event) => event.type), [
    "state", "run_end", "state", "turn_end", "model_changed",
    "thinking_changed", "compaction",
  ]);
  assert.equal(emitted[1].type === "run_end" && emitted[1].outcome, "error");
  assert.equal(emitted[2].type === "state" && emitted[2].state, "idle");
  assert.equal(emitted[4].type === "model_changed" && emitted[4].model?.id, "small");
  assert.equal(emitted[5].type === "thinking_changed" && emitted[5].level, "high");
  assert.equal(emitted[6].type === "compaction" && emitted[6].tokens_before, 100);
  assert.equal(activity.working, false);
});
