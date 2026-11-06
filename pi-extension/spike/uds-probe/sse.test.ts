import { test } from "node:test";
import assert from "node:assert/strict";

import { parseSseChunk } from "./sse.ts";

test("parses whole frames", () => {
  const result = parseSseChunk("", 'data: {"seq": 1}\n\ndata: {"seq": 2}\n\n');
  assert.deepEqual(result.events, ['{"seq": 1}', '{"seq": 2}']);
  assert.equal(result.buffer, "");
});

test("keeps an incomplete frame in the buffer", () => {
  const first = parseSseChunk("", 'data: {"seq": 1}\ndata: tail');
  assert.deepEqual(first.events, []);
  assert.equal(first.buffer, 'data: {"seq": 1}\ndata: tail');

  const second = parseSseChunk(first.buffer, '\n\ndata: {"seq": 2}\n\n');
  assert.deepEqual(second.events, ['{"seq": 1}\ntail', '{"seq": 2}']);
  assert.equal(second.buffer, "");
});

test("ignores comment-only frames", () => {
  const result = parseSseChunk("", ": heartbeat\n\n");
  assert.deepEqual(result.events, []);
  assert.equal(result.buffer, "");
});
