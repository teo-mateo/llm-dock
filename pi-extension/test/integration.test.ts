import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { Presence } from "../src/presence.ts";
import { startFakeServer } from "./fake-server.ts";

const realClock = {
  now: () => Date.now(),
  setTimeout: (fn: () => void, ms: number) => setTimeout(fn, ms),
  clearTimeout: (handle: unknown) => clearTimeout(handle as NodeJS.Timeout),
};

const helloFields = () => ({
  session_id: "integration-session",
  instance_id: "integration-instance",
  session_file: "/tmp/integration-session.jsonl",
  cwd: "/tmp",
  name: "integration",
  pid: 4242,
  model: { provider: "mistral", id: "mistral-small-latest" },
  thinking_level: "high",
  reason: "startup" as const,
  previous_session_id: "previous-session",
  parent_session_id: null,
  pi_version: "1.0.4",
  ext_version: "0.1.0",
});

async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

test("hello, heartbeats, re-hello after a server restart, then bye", { timeout: 10000 }, async () => {
  const dir = mkdtempSync(join(tmpdir(), "pi-remote-"));
  const socketPath = join(dir, "fake.sock");
  const fake = await startFakeServer(socketPath);

  const presence = new Presence({
    socketPath,
    enabled: true,
    clock: realClock,
    helloFields,
    heartbeatSample: () => ({
      state: "working",
      context: { tokens: 100, window: 2000, percent: 5 },
    }),
    heartbeatMs: 40,
    helloTimeoutMs: 1000,
    heartbeatTimeoutMs: 1000,
    byeTimeoutMs: 1000,
    initialBackoffMs: 50,
  });

  try {
    presence.start();
    await sleep(150);
    assert.equal(presence.status().state, "online");

  const hellos = fake.records.filter((record) => record.path === "/v1/hello");
  assert.ok(hellos.length >= 1);
  const hello = hellos[0].body as Record<string, any>;
  assert.equal(hello.protocol, 1);
  assert.equal(hello.type, "hello");
  assert.equal(hello.session_id, "integration-session");
  assert.equal(hello.instance_id, "integration-instance");
  assert.equal(hello.session_file, "/tmp/integration-session.jsonl");
  assert.equal(hello.cwd, "/tmp");
  assert.equal(hello.name, "integration");
  assert.equal(hello.pid, 4242);
  assert.deepEqual(hello.model, { provider: "mistral", id: "mistral-small-latest" });
  assert.equal(hello.thinking_level, "high");
  assert.equal(hello.reason, "startup");
  assert.equal(hello.previous_session_id, "previous-session");
  assert.equal(hello.pi_version, "1.0.4");
  assert.equal(hello.ext_version, "0.1.0");

  const heartbeats = fake.records.filter((record) => record.path === "/v1/heartbeat");
  assert.ok(heartbeats.length >= 2);
  const heartbeat = heartbeats[0].body as Record<string, any>;
  assert.equal(heartbeat.protocol, 1);
  assert.equal(heartbeat.type, "heartbeat");
  assert.equal(heartbeat.state, "working");
  assert.deepEqual(heartbeat.context, { tokens: 100, window: 2000, percent: 5 });

  fake.clearSessions();
  await sleep(150);
  assert.ok(fake.records.filter((record) => record.path === "/v1/hello").length >= 2);

  await presence.stop("test-shutdown");
  const byes = fake.records.filter((record) => record.path === "/v1/bye");
  assert.equal(byes.length, 1);
  assert.equal(byes[0].status, 200);
  assert.equal((byes[0].body as Record<string, any>).reason, "test-shutdown");
  } finally {
    await presence.stop("test-shutdown");
    await fake.close();
  }
});
