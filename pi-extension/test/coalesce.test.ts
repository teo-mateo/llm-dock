import { test } from "node:test";
import assert from "node:assert/strict";

import {
  DELTA_MAX_CHARS,
  DeltaCoalescer,
  MAX_TOOL_TEXT_BYTES,
  ToolThrottle,
  toolText,
} from "../src/coalesce.ts";

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

test("tool updates are throttled to four per second", () => {
  const throttle = new ToolThrottle();
  assert.equal(throttle.allow("call", 1000), true);
  assert.equal(throttle.allow("call", 1100), false);
  assert.equal(throttle.allow("call", 1250), true);
  throttle.done("call");
  assert.equal(throttle.allow("call", 1250), true);
});

test("tool text is truncated at 64 KB with a flag", () => {
  const short = toolText({ command: "echo hi" });
  assert.deepEqual(short, { text: '{"command":"echo hi"}', truncated: false });

  const long = toolText("x".repeat(MAX_TOOL_TEXT_BYTES + 1));
  assert.equal(long.truncated, true);
  assert.equal(Buffer.byteLength(long.text ?? ""), MAX_TOOL_TEXT_BYTES);

  assert.deepEqual(toolText(undefined), { text: null, truncated: false });
});
