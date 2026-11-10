import { test } from "node:test";
import assert from "node:assert/strict";

import {
  PROTOCOL_VERSION,
  buildBye,
  buildHeartbeat,
  buildEvents,
  buildHello,
  classifyResponse,
  parseResponse,
} from "../src/protocol.ts";

const helloFields = {
  session_id: "s1",
  instance_id: "i1",
  session_file: "/sessions/s1.jsonl",
  cwd: "/tmp",
  name: "probe",
  pid: 123,
  model: { provider: "mistral", id: "mistral-small-latest" },
  thinking_level: "high",
  reason: "startup" as const,
  previous_session_id: null,
  parent_session_id: null,
  pi_version: "1.0.4",
  ext_version: "0.1.0",
};

test("buildHello stamps protocol and type", () => {
  const frame = buildHello(helloFields);
  assert.equal(frame.protocol, PROTOCOL_VERSION);
  assert.equal(frame.type, "hello");
  assert.equal(frame.session_id, "s1");
  assert.deepEqual(frame.model, { provider: "mistral", id: "mistral-small-latest" });
});

test("buildHeartbeat stamps protocol and type", () => {
  const frame = buildHeartbeat({
    session_id: "s1",
    instance_id: "i1",
    state: "working",
    context: { tokens: 100, window: 2000, percent: 5 },
    sent_at: 42,
  });
  assert.equal(frame.protocol, PROTOCOL_VERSION);
  assert.equal(frame.type, "heartbeat");
  assert.equal(frame.state, "working");
  assert.equal(frame.sent_at, 42);
});

test("buildBye stamps protocol and type", () => {
  const frame = buildBye({ session_id: "s1", instance_id: "i1", reason: "shutdown" });
  assert.equal(frame.protocol, PROTOCOL_VERSION);
  assert.equal(frame.type, "bye");
  assert.equal(frame.reason, "shutdown");
});

test("parseResponse accepts a valid server response", () => {
  const response = parseResponse(JSON.stringify({ ok: true, protocol: 1, server_time: 1 }));
  assert.deepEqual(response, { ok: true, protocol: 1, server_time: 1 });
});

test("parseResponse rejects malformed bodies", () => {
  assert.equal(parseResponse("not json"), null);
  assert.equal(parseResponse(JSON.stringify({ ok: true })), null);
  assert.equal(parseResponse(JSON.stringify({ ok: "yes", protocol: 1 })), null);
  assert.equal(parseResponse(JSON.stringify(null)), null);
});

test("parseResponse carries error codes", () => {
  const response = parseResponse(JSON.stringify({ ok: false, protocol: 1, error: "unknown_session" }));
  assert.equal(response?.error, "unknown_session");
});

test("buildEvents stamps protocol and type", () => {
  const frame = buildEvents({ session_id: "s1", instance_id: "i1", events: [] });
  assert.equal(frame.protocol, PROTOCOL_VERSION);
  assert.equal(frame.type, "events");
  assert.deepEqual(frame.events, []);
});

test("classifyResponse distinguishes bad_frame from rejection", () => {
  assert.equal(classifyResponse(400, JSON.stringify({ ok: false, protocol: 1, error: "bad_frame" })), "bad_frame");
  assert.equal(classifyResponse(400, JSON.stringify({ ok: false, protocol: 1, error: "unsupported_protocol" })), "rejected");
  assert.equal(classifyResponse(404, JSON.stringify({ ok: false, protocol: 1, error: "unknown_session" })), "unknown_session");
});

test("parseResponse carries acked_seq", () => {
  const response = parseResponse(JSON.stringify({ ok: true, protocol: 1, acked_seq: 3 }));
  assert.equal(response?.acked_seq, 3);
});
