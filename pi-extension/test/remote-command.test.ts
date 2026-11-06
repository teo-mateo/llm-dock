import { test } from "node:test";
import assert from "node:assert/strict";

import { parseRemoteAction, statusText } from "../src/remote-command.ts";
import type { PresenceStatus } from "../src/presence-types.ts";

test("parses the /remote argument", () => {
  assert.equal(parseRemoteAction(""), "status");
  assert.equal(parseRemoteAction("  status  "), "status");
  assert.equal(parseRemoteAction("on"), "on");
  assert.equal(parseRemoteAction("off"), "off");
  assert.equal(parseRemoteAction("bogus"), "invalid");
});

test("formats online status", () => {
  const status: PresenceStatus = {
    state: "online",
    socketPath: "/tmp/x.sock",
    sessionId: "s1",
    instanceId: "i1",
    lastHeartbeatAt: Date.parse("2026-11-06T12:00:00.000Z"),
    nextAttemptAt: null,
    attempts: 0,
  };
  assert.equal(
    statusText(status),
    "pi-remote: online · socket /tmp/x.sock · session s1 · last heartbeat 2026-11-06T12:00:00.000Z · next attempt -",
  );
});

test("formats offline status with a retry", () => {
  const status: PresenceStatus = {
    state: "offline",
    socketPath: "/tmp/x.sock",
    sessionId: null,
    instanceId: null,
    lastHeartbeatAt: null,
    nextAttemptAt: Date.parse("2026-11-06T12:00:01.000Z"),
    attempts: 2,
  };
  assert.equal(
    statusText(status),
    "pi-remote: offline · socket /tmp/x.sock · session - · last heartbeat never · next attempt 2026-11-06T12:00:01.000Z",
  );
});
