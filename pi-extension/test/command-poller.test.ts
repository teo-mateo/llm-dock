import { test } from "node:test";
import assert from "node:assert/strict";

import { CommandPoller } from "../src/command-poller.ts";
import type { PresenceLike, PresenceState, PresenceStatus } from "../src/presence-types.ts";
import type { RequestFn, TransportResult } from "../src/transport.ts";
import { fakeClock, flush } from "./fake-clock.ts";

type TestPresence = PresenceLike & {
  setState: (state: PresenceState) => void;
  rejoined: () => number;
};

function makePresence(state: PresenceState): TestPresence {
  let current = state;
  let rejoined = 0;
  return {
    status: (): PresenceStatus => ({
      state: current,
      socketPath: "/tmp/test.sock",
      sessionId: "s1",
      instanceId: "i1",
      lastHeartbeatAt: null,
      nextAttemptAt: null,
      attempts: 0,
    }),
    rejoin: () => {
      rejoined += 1;
    },
    setState: (next) => {
      current = next;
    },
    rejoined: () => rejoined,
  };
}

type SeenRequest = {
  path: string;
  payload: Record<string, unknown>;
  timeout: number;
};

function scripted(responses: TransportResult[]): { request: RequestFn; requests: SeenRequest[] } {
  const requests: SeenRequest[] = [];
  const request: RequestFn = async (_socketPath, path, payload, timeoutMs) => {
    requests.push({ path, payload: payload as Record<string, unknown>, timeout: timeoutMs });
    const next = responses.shift();
    if (!next) throw new Error("no response");
    return next;
  };
  return { request, requests };
}

function pollResponse(commands: unknown[]): TransportResult {
  return {
    status: 200,
    body: JSON.stringify({ ok: true, protocol: 1, commands }),
  };
}

function resultsResponse(): TransportResult {
  return { status: 200, body: JSON.stringify({ ok: true, protocol: 1 }) };
}

const abortCommand = {
  command_id: "cmd-1",
  kind: "abort",
  args: {},
  issued_at: 1000,
};

test("polls only while online", async () => {
  const clock = fakeClock();
  const presence = makePresence("offline");
  const { request, requests } = scripted([pollResponse([])]);
  const poller = new CommandPoller({
    socketPath: "/tmp/test.sock",
    presence,
    clock,
    request,
    handlers: { abort: () => {} },
    waitMs: 10,
  });
  poller.start();
  await clock.advance(0);
  await flush();
  assert.equal(requests.length, 0);
  presence.setState("online");
  poller.start();
  await clock.advance(0);
  await flush();
  assert.ok(requests.length >= 1);
  assert.equal(requests[0].path, "/v1/commands/poll");
});

test("posts results after executing", async () => {
  const clock = fakeClock();
  const presence = makePresence("online");
  const { request, requests } = scripted([pollResponse([abortCommand]), resultsResponse()]);
  let executed = 0;
  const poller = new CommandPoller({
    socketPath: "/tmp/test.sock",
    presence,
    clock,
    request,
    handlers: { abort: () => { executed += 1; } },
    waitMs: 10,
  });
  poller.start();
  await clock.advance(0);
  await flush();
  assert.deepEqual(requests.map((entry) => entry.path), ["/v1/commands/poll", "/v1/command-results"]);
  assert.equal(executed, 1);
  assert.deepEqual(requests[1].payload.results, [
    { command_id: "cmd-1", ok: true, error: null },
  ]);
});

test("repeat command is not executed twice", async () => {
  const clock = fakeClock();
  const presence = makePresence("online");
  const { request, requests } = scripted([
    pollResponse([abortCommand]),
    resultsResponse(),
    pollResponse([abortCommand]),
    resultsResponse(),
  ]);
  let executed = 0;
  const poller = new CommandPoller({
    socketPath: "/tmp/test.sock",
    presence,
    clock,
    request,
    handlers: { abort: () => { executed += 1; } },
    waitMs: 10,
  });
  poller.start();
  await clock.advance(0);
  await flush();
  assert.equal(executed, 1);
  await clock.advance(0);
  await flush();
  assert.equal(requests.length, 4);
  assert.equal(executed, 1);
  assert.deepEqual(requests[3].payload.results, [
    { command_id: "cmd-1", ok: true, error: null },
  ]);
});

test("error backs off", async () => {
  const clock = fakeClock();
  const presence = makePresence("online");
  const { request, requests } = scripted([
    { status: 500, body: JSON.stringify({ ok: false, protocol: 1, error: "server_error" }) },
  ]);
  const poller = new CommandPoller({
    socketPath: "/tmp/test.sock",
    presence,
    clock,
    request,
    handlers: { abort: () => {} },
    waitMs: 10,
    initialBackoffMs: 1000,
  });
  poller.start();
  await clock.advance(0);
  await flush();
  assert.equal(requests.length, 1);
  assert.deepEqual(clock.pending(), [1000]);
});

test("404 rejoins", async () => {
  const clock = fakeClock();
  const presence = makePresence("online");
  const { request } = scripted([
    { status: 404, body: JSON.stringify({ ok: false, protocol: 1, error: "unknown_session" }) },
  ]);
  const poller = new CommandPoller({
    socketPath: "/tmp/test.sock",
    presence,
    clock,
    request,
    handlers: { abort: () => {} },
    waitMs: 10,
    initialBackoffMs: 1000,
  });
  poller.start();
  await clock.advance(0);
  await flush();
  assert.equal(presence.rejoined(), 1);
  assert.deepEqual(clock.pending(), [1000]);
});

test("pause and stop end the loop and cancel timers", async () => {
  const clock = fakeClock();
  const presence = makePresence("online");
  const { request, requests } = scripted([]);
  const poller = new CommandPoller({
    socketPath: "/tmp/test.sock",
    presence,
    clock,
    request,
    handlers: { abort: () => {} },
    waitMs: 10,
  });
  poller.start();
  assert.deepEqual(clock.pending(), [0]);
  poller.pause();
  assert.deepEqual(clock.pending(), []);
  await clock.advance(10);
  assert.equal(requests.length, 0);
  poller.start();
  assert.deepEqual(clock.pending(), [0]);
  poller.stop();
  assert.deepEqual(clock.pending(), []);
  await clock.advance(10);
  assert.equal(requests.length, 0);
});
