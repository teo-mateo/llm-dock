import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { createActivity } from "../src/activity.ts";
import { createSessionRuntime } from "../src/session-runtime.ts";
import { startFakeServer } from "./fake-server.ts";

async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

test("runtime pauses the mirror, resumes, and stops with bye", { timeout: 10000 }, async () => {
  const dir = mkdtempSync(join(tmpdir(), "pi-remote-runtime-"));
  const socketPath = join(dir, "fake.sock");
  const fake = await startFakeServer(socketPath);
  const notices: string[] = [];
  const ctx = {
    sessionManager: {
      getSessionId: () => "runtime-session",
      getSessionFile: () => null,
      getSessionName: () => null,
    },
    cwd: "/tmp",
    model: null,
    thinkingLevel: null,
    getContextUsage: () => null,
    ui: { notify: (message: string) => notices.push(message) },
  } as any;
  const runtime = createSessionRuntime({
    config: { enabled: true, socketPath, configPath: "" },
    ctx,
    event: { reason: "startup", previousSessionFile: null } as any,
    instanceId: "runtime-instance",
    extVersion: "0.1.0",
    piVersion: null,
    previousSessionId: null,
    activity: createActivity(),
  });

  try {
    await sleep(100);
    runtime.handle({ type: "input", text: "one", source: "interactive" } as any);
    await sleep(100);
    assert.deepEqual([...fake.events.get("runtime-session|runtime-instance")!.keys()], [1]);

    await runtime.pause();
    assert.equal(runtime.presence.status().state, "offline");
    runtime.handle({ type: "input", text: "while off", source: "interactive" } as any);
    await sleep(100);
    assert.deepEqual([...fake.events.get("runtime-session|runtime-instance")!.keys()], [1]);

    runtime.resume();
    await sleep(100);
    assert.equal(runtime.presence.status().state, "online");
    runtime.handle({ type: "input", text: "two", source: "interactive" } as any);
    await sleep(100);
    assert.deepEqual([...fake.events.get("runtime-session|runtime-instance")!.keys()], [1, 2]);

    await runtime.stop("shutdown");
    assert.equal(runtime.presence.status().state, "offline");
  } finally {
    await runtime.stop("test");
    await fake.close();
  }
});
