import { test } from "node:test";
import assert from "node:assert/strict";

import { EventStamper, stateBody, type WireEvent } from "../src/events.ts";
import { Outbox } from "../src/outbox.ts";
import type { PresenceState } from "../src/presence-types.ts";
import { EventSender } from "../src/sender.ts";
import type { TransportResult } from "../src/transport.ts";
import { fakeClock, flush } from "./fake-clock.ts";

function presence(state: PresenceState = "online") {
  let rejoinCalls = 0;
  return {
    status: () => ({
      state,
      socketPath: "/tmp/test.sock",
      sessionId: "s1",
      instanceId: "i1",
      lastHeartbeatAt: null,
      nextAttemptAt: null,
      attempts: 0,
    }),
    rejoin: () => { rejoinCalls += 1; state = "registering"; },
    rejoinCalls: () => rejoinCalls,
    setState: (next: PresenceState) => { state = next; },
  };
}

function scripted(handler: (payload: any) => { status: number; body: unknown } | Error) {
  const calls: any[] = [];
  const request = async (
    _socketPath: string,
    _path: string,
    payload: unknown,
    _timeoutMs: number,
  ): Promise<TransportResult> => {
    calls.push(payload);
    const result = handler(payload);
    if (result instanceof Error) throw result;
    return { status: result.status, body: JSON.stringify(result.body) };
  };
  return { calls, request };
}

function ackFor(payload: any) {
  const max = Math.max(...payload.events.map((event: any) => event.seq));
  return { status: 200, body: { ok: true, protocol: 1, acked_seq: max } };
}

function makeStates(count: number): WireEvent[] {
  const stamper = new EventStamper({ now: () => 1000 });
  return Array.from({ length: count }, () => stamper.stamp(stateBody("idle")));
}

test("enqueued events flush in order and are acknowledged", async () => {
  const clock = fakeClock();
  const transport = scripted(ackFor);
  const presenceState = presence();
  const sender = new EventSender({
    socketPath: "/tmp/test.sock",
    presence: presenceState,
    clock,
    request: transport.request,
  });

  const events = makeStates(2);
  sender.enqueue(events[0]);
  sender.enqueue(events[1]);
  await flush();

  assert.equal(transport.calls.length, 2);
  assert.deepEqual(transport.calls[0].events.map((event: any) => event.seq), [1]);
  assert.deepEqual(transport.calls[1].events.map((event: any) => event.seq), [2]);
});

test("one batch carries multiple queued events", async () => {
  const clock = fakeClock();
  const transport = scripted(ackFor);
  const presenceState = presence();
  const outbox = new Outbox(1000, () => clock.now());
  const events = makeStates(3);
  outbox.enqueue(events[0]);
  outbox.enqueue(events[1]);
  outbox.enqueue(events[2]);
  const sender = new EventSender({
    socketPath: "/tmp/test.sock",
    presence: presenceState,
    clock,
    outbox,
    request: transport.request,
  });

  sender.onOnline(0);
  await flush();
  assert.equal(transport.calls.length, 1);
  assert.deepEqual(transport.calls[0].events.map((event: any) => event.seq), [1, 2, 3]);
});

test("offline presence holds events until onOnline", async () => {
  const clock = fakeClock();
  const transport = scripted(ackFor);
  const presenceState = presence("offline");
  const sender = new EventSender({
    socketPath: "/tmp/test.sock",
    presence: presenceState,
    clock,
    request: transport.request,
  });

  sender.enqueue(makeStates(1)[0]);
  await flush();
  assert.equal(transport.calls.length, 0);

  presenceState.setState("online");
  sender.onOnline(0);
  await flush();
  assert.equal(transport.calls.length, 1);
});

test("404 on events triggers rejoin and keeps the events", async () => {
  const clock = fakeClock();
  const transport = scripted(() => ({
    status: 404,
    body: { ok: false, protocol: 1, error: "unknown_session" },
  }));
  const presenceState = presence();
  const sender = new EventSender({
    socketPath: "/tmp/test.sock",
    presence: presenceState,
    clock,
    request: transport.request,
  });

  sender.enqueue(makeStates(1)[0]);
  await flush();
  assert.equal(presenceState.rejoinCalls(), 1);
  assert.deepEqual(clock.pending(), []);
});

test("transport failure backs off with the shared backoff", async () => {
  const clock = fakeClock();
  let healthy = false;
  const transport = scripted((payload) => (healthy ? ackFor(payload) : new Error("ECONNREFUSED")));
  const presenceState = presence();
  const sender = new EventSender({
    socketPath: "/tmp/test.sock",
    presence: presenceState,
    clock,
    request: transport.request,
  });

  sender.enqueue(makeStates(1)[0]);
  await flush();
  assert.deepEqual(clock.pending(), [1000]);

  healthy = true;
  await clock.advance(1000);
  await flush();
  assert.equal(transport.calls.length, 2);
});

test("missing acked_seq is a retryable failure", async () => {
  const clock = fakeClock();
  const transport = scripted(() => ({ status: 200, body: { ok: true, protocol: 1 } }));
  const presenceState = presence();
  const sender = new EventSender({
    socketPath: "/tmp/test.sock",
    presence: presenceState,
    clock,
    request: transport.request,
  });

  sender.enqueue(makeStates(1)[0]);
  await flush();
  assert.deepEqual(clock.pending(), [1000]);
});


test("bad_frame discards and backs off instead of spinning", async () => {
  const clock = fakeClock();
  const transport = scripted(() => ({
    status: 400,
    body: { ok: false, protocol: 1, error: "bad_frame" },
  }));
  const presenceState = presence();
  const outbox = new Outbox(100, () => clock.now());
  const events = makeStates(2);
  outbox.enqueue(events[0]);
  outbox.enqueue(events[1]);
  const sender = new EventSender({
    socketPath: "/tmp/test.sock",
    presence: presenceState,
    clock,
    outbox,
    request: transport.request,
  });

  sender.onOnline(0);
  await flush();
  assert.equal(transport.calls.length, 1);
  assert.deepEqual(clock.pending(), [1000]);
  assert.equal(outbox.size, 1);
  assert.equal(outbox.unacked()[0].type, "gap");

  await clock.advance(1000);
  await flush();
  assert.equal(transport.calls.length, 2);
  assert.deepEqual(clock.pending(), [2000]);

  await clock.advance(2000);
  await flush();
  assert.equal(transport.calls.length, 3);
  assert.deepEqual(clock.pending(), [4000]);
});
