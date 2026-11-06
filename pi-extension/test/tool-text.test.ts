import { test } from "node:test";
import assert from "node:assert/strict";

import { MAX_TOOL_TEXT_BYTES, toolText } from "../src/tool-text.ts";

test("tool text is serialized and truncated at 64 KB", () => {
  assert.deepEqual(toolText({ command: "echo hi" }), {
    text: '{"command":"echo hi"}', truncated: false,
  });

  const long = toolText("x".repeat(MAX_TOOL_TEXT_BYTES + 1));
  assert.equal(long.truncated, true);
  assert.equal(Buffer.byteLength(long.text ?? ""), MAX_TOOL_TEXT_BYTES);

  assert.deepEqual(toolText(undefined), { text: null, truncated: false });
});
