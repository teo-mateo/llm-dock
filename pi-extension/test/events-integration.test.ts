import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { EventStamper, stateBody } from "../src/events.ts";
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
  parent_session_id: null,
  pi_version: null,
  ext_version: "0.1.0",
});

async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

test("events flush, survive a fake restart, and resend without loss", { timeout: 10000 }, async () => {
  const dir = mkdtempSync(join(tmpdir(), "pi-remote-events-"));
  const socketPath = join(dir, "fake.sock");
  const fake = await startFakeServer(socketPath);

  let sender: EventSender | undefined;
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
    onOnline: (ackedSeq) => sender?.onOnline(ackedSeq),
  });

  try {
    sender = new EventSender({
      socketPath,
      presence,
      clock: realClock,
      initialBackoffMs: 50,
    });

    presence.start();
    await sleep(100);
    assert.equal(presence.status().state, "online");

    const stamper = new EventStamper({ now: () => Date.now() });
    sender.enqueue(stamper.stamp(stateBody("idle")));
    sender.enqueue(stamper.stamp(stateBody("working")));
    await sleep(100);

    const key = "events-session|events-instance";
    const first = fake.events.get(key);
    assert.ok(first);
    assert.deepEqual([...first.keys()].sort((a, b) => a - b), [1, 2]);

    fake.clearSessions(true);
    sender.enqueue(stamper.stamp(stateBody("idle")));
    sender.enqueue(stamper.stamp(stateBody("working")));
    await sleep(200);

    const second = fake.events.get(key);
    assert.ok(second);
    assert.deepEqual([...second.keys()].sort((a, b) => a - b), [3, 4]);
  } finally {
    await sender?.stop();
    await presence.stop("test");
    await fake.close();
  }
});
