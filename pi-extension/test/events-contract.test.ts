import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { handleFrame, type EventStore, type Registry } from "./fake-server.ts";

type ContractCase = {
  path: string;
  now: number;
  request: Record<string, unknown>;
  status: number;
  response: unknown;
};

const cases = JSON.parse(
  readFileSync(new URL("./contract/events.json", import.meta.url), "utf8"),
) as ContractCase[];

test("golden events fixtures run in order", () => {
  const registry: Registry = new Map();
  const events: EventStore = new Map();
  for (const [index, entry] of cases.entries()) {
    const result = handleFrame(entry.path, entry.request, registry, entry.now, events);
    assert.equal(result.status, entry.status, `case ${index} ${entry.path} at ${entry.now}`);
    assert.deepEqual(result.payload, entry.response, `case ${index} ${entry.path} at ${entry.now}`);
  }
});

test("oversize events body is rejected", () => {
  const now = 1000;
  const registry: Registry = new Map([["s1|i1", { sessionId: "s1", instanceId: "i1", lastSeen: now }]]);
  const events: EventStore = new Map();
  const frame = {
    protocol: 1,
    type: "events",
    session_id: "s1",
    instance_id: "i1",
    events: [{
      type: "assistant_message",
      seq: 1,
      ts: now,
      text: "x".repeat(1_100_000),
      thinking: "",
      model: null,
      usage: null,
      stop_reason: "stop",
    }],
  };
  const result = handleFrame("/v1/events", frame, registry, now, events);
  assert.equal(result.status, 400);
  assert.deepEqual(result.payload, { ok: false, protocol: 1, error: "bad_frame" });
});
