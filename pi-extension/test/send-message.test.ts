import { test } from "node:test";
import assert from "node:assert/strict";

import { Delivery } from "../src/delivery.ts";
import { createSendMessageHandler } from "../src/send-message.ts";

function makePort(idle: boolean) {
  const sends: Array<{ text: string; mode: "turn" | "steer" }> = [];
  const notices: string[] = [];
  return {
    port: {
      isIdle: () => idle,
      send: (text: string, mode: "turn" | "steer") => { sends.push({ text, mode }); },
      notify: (text: string) => { notices.push(text); },
    },
    sends,
    notices,
  };
}

test("idle starts a turn", async () => {
  const { port, sends } = makePort(true);
  const delivery = new Delivery();
  const handler = createSendMessageHandler(port, delivery, () => 100);
  const result = await handler({ text: "hello" });
  assert.deepEqual(result, { command_id: "send-1", ok: true, error: null });
  assert.deepEqual(sends, [{ text: "hello", mode: "turn" }]);
  assert.equal(delivery.pending(), 0);
});

test("busy steers and tracks", async () => {
  const { port, sends } = makePort(false);
  const delivery = new Delivery();
  const handler = createSendMessageHandler(port, delivery, () => 100);
  const result = await handler({ text: "hello" });
  assert.equal(result.ok, true);
  assert.deepEqual(sends, [{ text: "hello", mode: "steer" }]);
  assert.equal(delivery.pending(), 1);
  assert.deepEqual(delivery.settle().map((entry) => entry.text), ["hello"]);
});

test("empty text is invalid_args", async () => {
  const { port, sends } = makePort(true);
  const delivery = new Delivery();
  const handler = createSendMessageHandler(port, delivery, () => 100);
  const result = await handler({ text: "   " });
  assert.deepEqual(result, { command_id: "send-invalid", ok: false, error: "invalid_args" });
  assert.equal(sends.length, 0);
  assert.equal(delivery.pending(), 0);
});

test("over-long text is invalid_args", async () => {
  const { port } = makePort(true);
  const delivery = new Delivery();
  const handler = createSendMessageHandler(port, delivery, () => 100);
  const result = await handler({ text: "x".repeat(32001) });
  assert.deepEqual(result, { command_id: "send-invalid", ok: false, error: "invalid_args" });
});

test("notifies the terminal", async () => {
  const { port, notices } = makePort(true);
  const delivery = new Delivery();
  const handler = createSendMessageHandler(port, delivery, () => 100);
  const text = "a".repeat(100);
  await handler({ text });
  assert.deepEqual(notices, ["📱 " + text.slice(0, 80)]);
});

test("leading slash is sent as text", async () => {
  const { port, sends } = makePort(true);
  const delivery = new Delivery();
  const handler = createSendMessageHandler(port, delivery, () => 100);
  await handler({ text: "/not-a-command" });
  assert.deepEqual(sends, [{ text: "/not-a-command", mode: "turn" }]);
});

test("tracks the supplied command id", async () => {
  const { port } = makePort(false);
  const delivery = new Delivery();
  const handler = createSendMessageHandler(port, delivery, () => 100);
  await handler({ text: "hello" }, "remote-42");
  assert.equal(delivery.settle()[0].commandId, "remote-42");
});
