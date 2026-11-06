import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { PATHS, type Command } from "../src/protocol.ts";
import { commandKey, FakeCommands, handleCommandResults, handleCommandsPoll } from "./fake-commands.ts";
import { handleFrame, type Frame, type Registry } from "./fake-server.ts";

type ContractCase = {
  path: string;
  now: number;
  request: Record<string, unknown>;
  enqueue?: Command;
  status: number;
  response: unknown;
};

const cases = JSON.parse(
  readFileSync(new URL("./contract/commands.json", import.meta.url), "utf8"),
) as ContractCase[];

test("golden command fixtures run through the fake", async () => {
  const registry: Registry = new Map();
  const commands = new FakeCommands();
  for (const [index, entry] of cases.entries()) {
    if (entry.enqueue) {
      const key = commandKey(
        String(entry.request.session_id),
        String(entry.request.instance_id),
      );
      commands.enqueue(key, entry.enqueue);
    }
    let result: { status: number; payload: unknown };
    if (entry.path === PATHS.commandsPoll) {
      result = await handleCommandsPoll(entry.request, registry, commands, entry.now, async () => {});
    } else if (entry.path === PATHS.commandResults) {
      result = handleCommandResults(entry.request, registry, commands, entry.now);
    } else {
      result = handleFrame(entry.path, entry.request as Frame, registry, entry.now);
    }
    assert.equal(result.status, entry.status, `case ${index} ${entry.path} at ${entry.now}`);
    assert.deepEqual(result.payload, entry.response, `case ${index} ${entry.path} at ${entry.now}`);
  }
});
