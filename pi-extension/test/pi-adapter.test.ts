import { test } from "node:test";
import assert from "node:assert/strict";

import type { ExtensionContext } from "@earendil-works/pi-coding-agent";

import { createActivity } from "../src/activity.ts";
import { heartbeatSampleFrom, helloFieldsFrom, parentSessionIdFrom } from "../src/pi-adapter.ts";

function fakeCtx(): ExtensionContext {
  return {
    sessionManager: {
      getSessionId: () => "s1",
      getSessionFile: () => "/tmp/s1.jsonl",
      getSessionName: () => "probe",
    },
    cwd: "/tmp",
    model: { provider: "mistral", id: "mistral-small-latest" },
    thinkingLevel: "high",
    getContextUsage: () => ({ tokens: 5, contextWindow: 100, percent: 5 }),
  } as unknown as ExtensionContext;
}

test("maps an ExtensionContext to hello fields", () => {
  const fields = helloFieldsFrom(fakeCtx(), {
    instanceId: "i1",
    extVersion: "0.1.0",
    piVersion: "1.0.4",
    previousSessionId: "prev",
    parentSessionId: null,
    reason: "resume",
  });
  assert.equal(fields.session_id, "s1");
  assert.equal(fields.instance_id, "i1");
  assert.equal(fields.session_file, "/tmp/s1.jsonl");
  assert.equal(fields.cwd, "/tmp");
  assert.equal(fields.name, "probe");
  assert.equal(fields.model?.provider, "mistral");
  assert.equal(fields.model?.id, "mistral-small-latest");
  assert.equal(fields.thinking_level, "high");
  assert.equal(fields.reason, "resume");
  assert.equal(fields.previous_session_id, "prev");
  assert.equal(fields.parent_session_id, null);
  assert.equal(fields.pi_version, "1.0.4");
  assert.equal(fields.ext_version, "0.1.0");
  assert.equal(fields.pid, process.pid);
});

test("maps activity and usage to a heartbeat sample", () => {
  const activity = createActivity();
  activity.working = true;
  const sample = heartbeatSampleFrom(fakeCtx(), activity);
  assert.equal(sample.state, "working");
  assert.deepEqual(sample.context, { tokens: 5, window: 100, percent: 5 });
});

test("missing model and usage become nulls", () => {
  const ctx = {
    sessionManager: {
      getSessionId: () => "s1",
      getSessionFile: () => undefined,
      getSessionName: () => undefined,
    },
    cwd: "/tmp",
    model: undefined,
    thinkingLevel: undefined,
    getContextUsage: () => undefined,
  } as unknown as ExtensionContext;
  const fields = helloFieldsFrom(ctx, {
    instanceId: "i1",
    extVersion: "0.1.0",
    piVersion: null,
    previousSessionId: null,
    parentSessionId: null,
    reason: "startup",
  });
  assert.equal(fields.session_file, null);
  assert.equal(fields.name, null);
  assert.equal(fields.model, null);
  assert.equal(fields.thinking_level, null);
  assert.equal(fields.pi_version, null);
  assert.equal(heartbeatSampleFrom(ctx, createActivity()).context, null);
});

test("reads the parent session id from a subagent child process", () => {
  assert.equal(
    parentSessionIdFrom({ PI_SUBAGENT_CHILD: "1", PI_SUBAGENT_PARENT_SESSION: "root-session" }),
    "root-session",
  );
  assert.equal(
    parentSessionIdFrom({ PI_SUBAGENT_CHILD: "1", PI_SUBAGENT_PARENT_SESSION: "  root-session  " }),
    "root-session",
  );
});

test("a root session has no parent", () => {
  assert.equal(parentSessionIdFrom({}), null);
  assert.equal(parentSessionIdFrom({ PI_SUBAGENT_PARENT_SESSION: "root-session" }), null);
  assert.equal(
    parentSessionIdFrom({ PI_SUBAGENT_CHILD: "0", PI_SUBAGENT_PARENT_SESSION: "root-session" }),
    null,
  );
});

test("a child without a usable parent id reports none", () => {
  assert.equal(parentSessionIdFrom({ PI_SUBAGENT_CHILD: "1" }), null);
  assert.equal(parentSessionIdFrom({ PI_SUBAGENT_CHILD: "1", PI_SUBAGENT_PARENT_SESSION: "" }), null);
  assert.equal(parentSessionIdFrom({ PI_SUBAGENT_CHILD: "1", PI_SUBAGENT_PARENT_SESSION: "   " }), null);
});

test("the parent session id reaches the hello frame", () => {
  const fields = helloFieldsFrom(fakeCtx(), {
    instanceId: "i1",
    extVersion: "0.2.0",
    piVersion: null,
    previousSessionId: null,
    parentSessionId: "root-session",
    reason: "startup",
  });
  assert.equal(fields.parent_session_id, "root-session");
});
