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
    extVersion: "0.1.0",
    piVersion: null,
    previousSessionId: null,
    parentSessionId: null,
    activity: createActivity(),
  });

  try {
    await sleep(100);
    const instanceId = runtime.presence.status().instanceId;
    assert.ok(instanceId);
    runtime.handle({ type: "input", text: "one", source: "interactive" } as any);
    await sleep(100);
    assert.deepEqual([...fake.events.get(`${runtime.presence.status().sessionId}|${instanceId}`)!.keys()], [1]);

    await runtime.pause();
    assert.equal(runtime.presence.status().state, "offline");
    runtime.handle({ type: "input", text: "while off", source: "interactive" } as any);
    await sleep(100);
    assert.deepEqual([...fake.events.get(`${runtime.presence.status().sessionId}|${instanceId}`)!.keys()], [1]);

    runtime.resume();
    await sleep(100);
    assert.equal(runtime.presence.status().state, "online");
    runtime.handle({ type: "input", text: "two", source: "interactive" } as any);
    await sleep(100);
    assert.deepEqual([...fake.events.get(`${runtime.presence.status().sessionId}|${instanceId}`)!.keys()], [1, 2]);

    await runtime.stop("shutdown");
    assert.equal(runtime.presence.status().state, "offline");
  } finally {
    await runtime.stop("test");
    await fake.close();
  }
});

test("a switched runtime gets a fresh instance stream", { timeout: 10000 }, async () => {
  const dir = mkdtempSync(join(tmpdir(), "pi-remote-switch-"));
  const socketPath = join(dir, "fake.sock");
  const fake = await startFakeServer(socketPath);
  const ctx = {
    sessionManager: {
      getSessionId: () => "switch-session",
      getSessionFile: () => null,
      getSessionName: () => null,
    },
    cwd: "/tmp",
    model: null,
    thinkingLevel: null,
    getContextUsage: () => null,
    ui: { notify: () => {} },
  } as any;
  const options = {
    config: { enabled: true, socketPath, configPath: "" },
    ctx,
    event: { reason: "resume", previousSessionFile: null } as any,
    extVersion: "0.1.0",
    piVersion: null,
    previousSessionId: null,
    parentSessionId: null,
    activity: createActivity(),
  };
  const first = createSessionRuntime(options);
  let second: ReturnType<typeof createSessionRuntime> | undefined;
  try {
    await sleep(100);
    const firstInstance = first.presence.status().instanceId;
    assert.ok(firstInstance);
    first.handle({ type: "input", text: "one", source: "interactive" } as any);
    await sleep(100);
    assert.deepEqual([...fake.events.get(`switch-session|${firstInstance}`)!.keys()], [1]);

    await first.stop("switch");
    second = createSessionRuntime(options);
    await sleep(100);
    const secondInstance = second.presence.status().instanceId;
    assert.ok(secondInstance);
    assert.notEqual(secondInstance, firstInstance);
    second.handle({ type: "input", text: "one", source: "interactive" } as any);
    await sleep(100);
    assert.deepEqual([...fake.events.get(`switch-session|${secondInstance}`)!.keys()], [1]);
  } finally {
    await second?.stop("test");
    await first.stop("test");
    await fake.close();
  }
});

test("answer_prompt is dispatched through the command poller", { timeout: 10000 }, async () => {
  const dir = mkdtempSync(join(tmpdir(), "pi-remote-prompt-"));
  const socketPath = join(dir, "fake.sock");
  const fake = await startFakeServer(socketPath);
  const ctx = {
    sessionManager: {
      getSessionId: () => "prompt-session",
      getSessionFile: () => null,
      getSessionName: () => null,
    },
    cwd: "/tmp",
    model: null,
    thinkingLevel: null,
    getContextUsage: () => null,
    ui: { notify: () => {} },
  } as any;
  const runtime = createSessionRuntime({
    config: { enabled: true, socketPath, configPath: "" },
    ctx,
    event: { reason: "startup", previousSessionFile: null } as any,
    extVersion: "0.1.0",
    piVersion: null,
    previousSessionId: null,
    parentSessionId: null,
    activity: createActivity(),
  });

  try {
    await sleep(150);
    const key = `prompt-session|${runtime.presence.status().instanceId}`;
    runtime.remotePrompts.open({
      prompt_id: "tool-call-1",
      kind: "select",
      title: "Which port",
      message: "",
      options: ["3301"],
      allow_free_text: false,
      timeout_ms: null,
    });
    await sleep(150);
    const promptFrames = () => [...fake.events.get(key)!.values()]
      .filter((event) => String(event.type).startsWith("prompt_"))
      .map((event) => `${event.type}:${event.prompt_id}`);
    assert.deepEqual(promptFrames(), ["prompt_open:tool-call-1"]);

    fake.commands.enqueue(key, fake.commands.answerPromptCommand("tool-call-1", "3301"));
    await sleep(300);
    assert.deepEqual(promptFrames(), ["prompt_open:tool-call-1", "prompt_closed:tool-call-1"]);
    assert.deepEqual(fake.commands.results.get("prompt-1"), {
      command_id: "prompt-1", ok: true, error: null,
    });

    fake.commands.enqueue(key, fake.commands.answerPromptCommand("gone", "x"));
    await sleep(300);
    assert.deepEqual(fake.commands.results.get("prompt-2"), {
      command_id: "prompt-2", ok: false, error: "prompt_unknown",
    });
    assert.deepEqual(promptFrames(), ["prompt_open:tool-call-1", "prompt_closed:tool-call-1"]);
  } finally {
    await runtime.stop("test");
    await fake.close();
  }
});
