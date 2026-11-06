import { test } from "node:test";
import assert from "node:assert/strict";

import { Presence } from "../src/presence.ts";
import type { TransportResult } from "../src/transport.ts";

const helloFields = () => ({
  session_id: "s1",
  instance_id: "i1",
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

const heartbeatSample = () => ({ state: "idle" as const, context: null });

function fakeClock(start = 0) {
  let now = start;
  let seq = 0;
  const timers = new Map<number, { at: number; fn: () => void }>();
  return {
    now: () => now,
    setTimeout: (fn: () => void, ms: number) => {
      const id = ++seq;
      timers.set(id, { at: now + ms, fn });
      return id;
    },
    clearTimeout: (handle: unknown) => {
      timers.delete(handle as number);
    },
    async advance(ms: number) {
      now += ms;
      for (;;) {
        const due = [...timers.entries()]
          .filter(([, timer]) => timer.at <= now)
          .sort((a, b) => a[1].at - b[1].at);
        if (due.length === 0) return;
        for (const [id, timer] of due) {
          timers.delete(id);
          timer.fn();
          await Promise.resolve();
        }
      }
    },
    pending: () => [...timers.values()].map((timer) => timer.at - now).sort((a, b) => a - b),
  };
}

async function flush(): Promise<void> {
  for (let i = 0; i < 10; i += 1) await Promise.resolve();
}

function scripted(handler: (path: string, body: unknown) => { status: number; body: unknown } | Error) {
  const calls: { path: string; payload: any; timeoutMs: number }[] = [];
  const request = async (
    socketPath: string,
    path: string,
    payload: unknown,
    timeoutMs: number,
  ): Promise<TransportResult> => {
    calls.push({ path, payload, timeoutMs });
    const result = handler(path, payload);
    if (result instanceof Error) throw result;
    return { status: result.status, body: JSON.stringify(result.body) };
  };
  return { calls, request };
}

function makePresence(
  clock: ReturnType<typeof fakeClock>,
  request: ReturnType<typeof scripted>["request"],
  extra: { enabled?: boolean; notices?: string[]; states?: string[] } = {},
) {
  return new Presence({
    socketPath: "/tmp/test.sock",
    enabled: extra.enabled ?? true,
    clock,
    helloFields,
    heartbeatSample,
    request,
    onNotice: (message) => extra.notices?.push(message),
    onStateChange: (state) => extra.states?.push(state),
  });
}

test("registers with hello, then heartbeats every 15 s", async () => {
  const clock = fakeClock();
  const transport = scripted(() => ({ status: 200, body: { ok: true, protocol: 1 } }));
  const presence = makePresence(clock, transport.request);

  presence.start();
  await flush();
  assert.equal(presence.status().state, "online");
  assert.deepEqual(transport.calls.map((call) => call.path), ["/v1/hello"]);
  assert.equal(transport.calls[0].payload.protocol, 1);
  assert.equal(transport.calls[0].payload.type, "hello");
  assert.equal(transport.calls[0].payload.session_id, "s1");
  assert.equal(transport.calls[0].timeoutMs, 3000);

  await clock.advance(15000);
  await flush();
  assert.deepEqual(transport.calls.map((call) => call.path), ["/v1/hello", "/v1/heartbeat"]);
  assert.equal(transport.calls[1].payload.state, "idle");
  assert.equal(presence.status().lastHeartbeatAt, 15000);
  assert.deepEqual(clock.pending(), [15000]);
});

test("a second start does not register twice", async () => {
  const clock = fakeClock();
  const transport = scripted(() => ({ status: 200, body: { ok: true, protocol: 1 } }));
  const presence = makePresence(clock, transport.request);

  presence.start();
  presence.start();
  await flush();
  assert.equal(transport.calls.length, 1);
});

test("unknown_session on a heartbeat triggers a fresh hello", async () => {
  const clock = fakeClock();
  const transport = scripted((path) => {
    if (path === "/v1/hello") return { status: 200, body: { ok: true, protocol: 1 } };
    return { status: 404, body: { ok: false, protocol: 1, error: "unknown_session" } };
  });
  const presence = makePresence(clock, transport.request);

  presence.start();
  await flush();
  await clock.advance(15000);
  await flush();
  assert.deepEqual(transport.calls.map((call) => call.path), ["/v1/hello", "/v1/heartbeat", "/v1/hello"]);
  assert.equal(presence.status().state, "online");
});

test("absent dashboard backs off 1 s to a 30 s cap and notices once", async () => {
  const clock = fakeClock();
  const transport = scripted(() => new Error("ECONNREFUSED"));
  const notices: string[] = [];
  const presence = makePresence(clock, transport.request, { notices });

  presence.start();
  await flush();
  assert.equal(presence.status().state, "offline");
  assert.deepEqual(clock.pending(), [1000]);

  await clock.advance(1000);
  await flush();
  assert.deepEqual(clock.pending(), [2000]);
  await clock.advance(2000);
  await flush();
  assert.deepEqual(clock.pending(), [4000]);
  await clock.advance(4000);
  await flush();
  assert.deepEqual(clock.pending(), [8000]);
  await clock.advance(8000);
  await flush();
  assert.deepEqual(clock.pending(), [16000]);
  await clock.advance(16000);
  await flush();
  assert.deepEqual(clock.pending(), [30000]);
  await clock.advance(30000);
  await flush();
  assert.deepEqual(clock.pending(), [30000]);

  assert.equal(presence.status().attempts, 7);
  assert.equal(notices.filter((notice) => notice.includes("unreachable")).length, 1);
});

test("recovery after the dashboard returns emits one notice", async () => {
  const clock = fakeClock();
  let healthy = false;
  const transport = scripted(() =>
    healthy ? { status: 200, body: { ok: true, protocol: 1 } } : new Error("ECONNREFUSED"),
  );
  const notices: string[] = [];
  const presence = makePresence(clock, transport.request, { notices });

  presence.start();
  await flush();
  assert.equal(notices.length, 1);

  healthy = true;
  await clock.advance(1000);
  await flush();
  assert.equal(presence.status().state, "online");
  assert.equal(notices.filter((notice) => notice.includes("reachable again")).length, 1);
});

test("stop during backoff cancels the retry and is idempotent", async () => {
  const clock = fakeClock();
  const transport = scripted(() => new Error("ECONNREFUSED"));
  const presence = makePresence(clock, transport.request);

  presence.start();
  await flush();
  await clock.advance(1000);
  await flush();
  assert.deepEqual(clock.pending(), [2000]);

  const callsBefore = transport.calls.length;
  await presence.stop("test");
  assert.equal(presence.status().state, "offline");
  assert.deepEqual(clock.pending(), []);

  await clock.advance(10000);
  await flush();
  assert.equal(transport.calls.length, callsBefore);

  await presence.stop("test");
});

test("stop online sends bye with the reason and a 1 s timeout", async () => {
  const clock = fakeClock();
  const transport = scripted(() => ({ status: 200, body: { ok: true, protocol: 1 } }));
  const presence = makePresence(clock, transport.request);

  presence.start();
  await flush();
  await presence.stop("shutdown");

  const bye = transport.calls[transport.calls.length - 1];
  assert.equal(bye.path, "/v1/bye");
  assert.equal(bye.payload.reason, "shutdown");
  assert.equal(bye.timeoutMs, 1000);
  assert.equal(presence.status().state, "offline");
});

test("disabled config never contacts the dashboard", async () => {
  const clock = fakeClock();
  const transport = scripted(() => ({ status: 200, body: { ok: true, protocol: 1 } }));
  const presence = makePresence(clock, transport.request, { enabled: false });

  presence.start();
  await flush();
  assert.equal(presence.status().state, "disabled");
  assert.equal(transport.calls.length, 0);
});
