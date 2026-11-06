import { test } from "node:test";
import assert from "node:assert/strict";

import { sessionIdFromFile } from "../src/session.ts";

test("derives the session id from a pi session file", () => {
  assert.equal(
    sessionIdFromFile("/home/t/.pi/agent/sessions/--tmp--/2024-12-03T14-00-00_01a1b09a-7898-753a-b9fb-f052686cf087.jsonl"),
    "01a1b09a-7898-753a-b9fb-f052686cf087",
  );
});

test("returns null for missing paths", () => {
  assert.equal(sessionIdFromFile(undefined), null);
  assert.equal(sessionIdFromFile(null), null);
  assert.equal(sessionIdFromFile(""), null);
});

test("falls back to the whole stem when there is no underscore", () => {
  assert.equal(sessionIdFromFile("/sessions/2024-12-03T14-00-00.jsonl"), "2024-12-03T14-00-00");
});
