import { test } from "node:test";
import assert from "node:assert/strict";

import { DELTA_MAX_CHARS, DeltaCoalescer } from "../src/coalesce.ts";

test("text and thinking deltas coalesce by 100 ms", () => {
  const coalescer = new DeltaCoalescer();
  assert.deepEqual(coalescer.addText("hel", 1000), []);
  assert.deepEqual(coalescer.addThinking("th", 1050), []);
  assert.deepEqual(coalescer.addText("lo", 1100), [{ text: "hel", thinking: "th" }]);
  assert.deepEqual(coalescer.flush(1200), [{ text: "lo", thinking: "" }]);
});

test("coalescing flushes at 2 KB", () => {
  const coalescer = new DeltaCoalescer();
  const chunk = "x".repeat(DELTA_MAX_CHARS);
  assert.deepEqual(coalescer.addText(chunk, 1000), [{ text: chunk, thinking: "" }]);
});

test("flush is empty when nothing is pending", () => {
  const coalescer = new DeltaCoalescer();
  assert.deepEqual(coalescer.flush(1000), []);
});
