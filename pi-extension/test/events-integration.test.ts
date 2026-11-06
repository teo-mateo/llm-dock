import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { stateEvent } from "../src/events.ts";
import { Presence } from "../src/presence.ts";
import { EventSender } from "../src/sender.ts";
import { startFakeServer } from "./fake-server.ts";

const realClock = {
  now: () => Date.now(),
  setTimeout: (fn: () => void, ms: number) => setTimeout(fn, ms),
  clearTimeout: (handle: unknown) => clearTimeout(handle as NodeJS.Timeout),
};

const helloFields = () => ({
  session_id: "events-session",
  instance_id: "events-instance",
  session_file: null,
  cwd: "/tmp",
  name: null,
  pid: 1,
  model: null,
  thinking_level: null,
  reason: "startup" as const,
  previous_session_id: null,
  pi_version: null,
  ext_version: "0.1.0",
});

async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

test("events flush, survive a fake restart, and resend without loss", async () => {
  const dir = mkdtempSync(join(tmpdir(), "pi-remote-events-"));
  const socketPath = join(dir, "fake.sock");
  const fake = await startFakeServer(socketPath);

  let sender: EventSender;
  const presence = new Presence({
    socketPath,
    enabled: true,
    clock: realClock,
    helloFields,
    heartbeatSample: () => ({ state: "idle", context: null }),
    heartbeatMs: 5000,
    helloTimeoutMs: 1000,
    heartbeatTimeoutMs: 1000,
    byeTimeoutMs: 1000,
    initialBackoffMs: 50,
    onOnline: () => sender.onOnline(),
  });
  sender = new EventSender({
    socketPath,
    presence,
    clock: realClock,
    initialBackoffMs: 50,
  });

  presence.start();
  await sleep(100);
  assert.equal(presence.status().state, "online");

  sender.enqueue(stateEvent(1, Date.now(), "idle"));
  sender.enqueue(stateEvent(2, Date.now(), "working"));
  await sleep(100);

  const key = "events-session|events-instance";
  const first = fake.events.get(key);
  assert.ok(first);
  assert.deepEqual([...first.keys()].sort((a, b) => a - b), [1, 2]);

  fake.clearSessions();
  sender.enqueue(stateEvent(3, Date.now(), "idle"));
  await sleep(200);

  const second = fake.events.get(key);
  assert.ok(second);
  assert.deepEqual([...second.keys()].sort((a, b) => a - b), [1, 2, 3]);

  await presence.stop("test");
  await fake.close();
});
