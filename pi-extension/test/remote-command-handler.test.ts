import { test } from "node:test";
import assert from "node:assert/strict";

import { handleRemoteCommand } from "../src/remote-command-handler.ts";

function ctx(notices: string[]) {
  return { ui: { notify: (message: string) => notices.push(message) } } as any;
}

test("off pauses the runtime", async () => {
  const notices: string[] = [];
  let paused = 0;
  const runtime = {
    presence: { status: () => ({ state: "online", socketPath: "/tmp", sessionId: "s", instanceId: "i", lastHeartbeatAt: null, nextAttemptAt: null, attempts: 0 }) },
    pause: async () => { paused += 1; },
    resume: () => {},
  } as any;
  await handleRemoteCommand("off", ctx(notices), runtime);
  assert.equal(paused, 1);
  assert.ok(notices.some((notice) => notice.includes("off")));
});

test("on resumes unless disabled", async () => {
  const notices: string[] = [];
  let resumed = 0;
  const runtime = {
    presence: { status: () => ({ state: "online", socketPath: "/tmp", sessionId: "s", instanceId: "i", lastHeartbeatAt: null, nextAttemptAt: null, attempts: 0 }) },
    pause: async () => {},
    resume: () => { resumed += 1; },
  } as any;
  await handleRemoteCommand("on", ctx(notices), runtime);
  assert.equal(resumed, 1);

  const disabled = {
    presence: { status: () => ({ state: "disabled", socketPath: "/tmp", sessionId: null, instanceId: null, lastHeartbeatAt: null, nextAttemptAt: null, attempts: 0 }) },
    pause: async () => {},
    resume: () => { resumed += 1; },
  } as any;
  await handleRemoteCommand("on", ctx(notices), disabled);
  assert.equal(resumed, 1);
});
