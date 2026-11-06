import { test } from "node:test";
import assert from "node:assert/strict";

import { CommandDedupe, dispatch } from "../src/commands.ts";
import type { Command } from "../src/protocol.ts";

function command(id: string, kind: string): Command {
  return { command_id: id, kind, args: {}, issued_at: 1000 };
}

test("dispatch runs the handler", async () => {
  let calls = 0;
  const result = await dispatch(command("c1", "abort"), {
    abort: () => { calls += 1; },
  });
  assert.deepEqual(result, { command_id: "c1", ok: true, error: null });
  assert.equal(calls, 1);
});

test("unknown kind is unsupported", async () => {
  const result = await dispatch(command("c1", "unknown"), {
    abort: () => {},
  });
  assert.deepEqual(result, { command_id: "c1", ok: false, error: "unsupported_command" });
});

test("throwing handler is failed", async () => {
  const result = await dispatch(command("c1", "abort"), {
    abort: () => { throw new Error("boom"); },
  });
  assert.deepEqual(result, { command_id: "c1", ok: false, error: "failed" });
});

test("dedupe returns stored result and does not rerun", () => {
  const dedupe = new CommandDedupe(2);
  const stored = { command_id: "c1", ok: true, error: null };
  dedupe.record(stored);
  assert.deepEqual(dedupe.seen("c1"), stored);
});

test("dedupe evicts beyond capacity", () => {
  const dedupe = new CommandDedupe(2);
  dedupe.record({ command_id: "c1", ok: true, error: null });
  dedupe.record({ command_id: "c2", ok: true, error: null });
  dedupe.record({ command_id: "c3", ok: true, error: null });
  assert.equal(dedupe.seen("c1"), undefined);
  assert.equal(dedupe.seen("c2")?.command_id, "c2");
  assert.equal(dedupe.seen("c3")?.command_id, "c3");
});
