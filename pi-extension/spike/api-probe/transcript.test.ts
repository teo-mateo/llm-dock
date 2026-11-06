import { test } from "node:test";
import assert from "node:assert/strict";

import { entryText, findToken, hasToolCalls, summarizeEntry, textOfContent } from "./transcript.ts";

test("textOfContent handles strings and text parts", () => {
  assert.equal(textOfContent("hello"), "hello");
  assert.equal(textOfContent([{ type: "text", text: "a" }, { type: "thinking", text: "b" }]), "a b");
  assert.equal(textOfContent(undefined), "");
  assert.equal(textOfContent([{ type: "toolCall", id: "x" }]), "");
});

test("findToken looks through message content", () => {
  const entries = [
    { type: "message", message: { role: "user", content: [{ type: "text", text: "probe-abc here" }] } },
    { type: "message", message: { role: "assistant", content: "nothing" } },
  ];
  assert.equal(findToken(entries, "probe-abc"), true);
  assert.equal(findToken(entries, "probe-zzz"), false);
});

test("entryText falls back to top-level content", () => {
  assert.equal(entryText({ content: "top level" }), "top level");
  assert.equal(entryText({}), "");
});

test("hasToolCalls only counts toolCall parts", () => {
  assert.equal(hasToolCalls({ content: [{ type: "text", text: "hi" }] }), false);
  assert.equal(hasToolCalls({ content: [{ type: "toolCall", id: "1" }] }), true);
  assert.equal(hasToolCalls({ content: "plain" }), false);
});

test("summarizeEntry names the role and previews text", () => {
  assert.equal(summarizeEntry({ message: { role: "user", content: "hello" } }), 'user "hello"');
  assert.equal(summarizeEntry({ type: "custom" }), "custom");
});
