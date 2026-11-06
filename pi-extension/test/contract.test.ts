import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { handleFrame, type Registry } from "./fake-server.ts";

type ContractCase = {
  path: string;
  now: number;
  request: Record<string, unknown>;
  status: number;
  response: unknown;
};

const cases = JSON.parse(
  readFileSync(new URL("./contract/frames.json", import.meta.url), "utf8"),
) as ContractCase[];

test("golden contract fixtures run in order", () => {
  const registry: Registry = new Map();
  for (const [index, entry] of cases.entries()) {
    const result = handleFrame(entry.path, entry.request, registry, entry.now);
    assert.equal(result.status, entry.status, `case ${index} ${entry.path} at ${entry.now}`);
    assert.deepEqual(result.payload, entry.response, `case ${index} ${entry.path} at ${entry.now}`);
  }
});
