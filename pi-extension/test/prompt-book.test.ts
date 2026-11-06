import { test} from "node:test";
import assert from "node:assert/strict";

import { PromptBook, validatePromptValue, type PromptSpec } from "../src/prompt-book.ts";

function spec(overrides: Partial<PromptSpec> = {}): PromptSpec {
  return {
    prompt_id: "p1",
    kind: "input",
    title: "Which one",
    message: "",
    options: [],
    allow_free_text: false,
    timeout_ms: null,
    ...overrides,
  };
}

test("first answer wins and a later answer never resolves", async () => {
  const book = new PromptBook();
  book.open(spec());
  const waiting = book.waitFor("p1");
  assert.equal(book.answer("p1", "first", "remote"), "answered");
  assert.deepEqual(await waiting, { value: "first", source: "remote" });
  assert.equal(book.answer("p1", "second", "terminal"), "already_answered");
  assert.equal(book.status("p1"), "answered");
  assert.deepEqual(await book.waitFor("p1"), { value: "first", source: "remote" });
});

test("answer on an unknown prompt reports unknown", () => {
  const book = new PromptBook();
  assert.equal(book.answer("nope", "x", "remote"), "unknown");
});

test("values are validated per kind", () => {
  assert.equal(validatePromptValue("confirm", spec({ kind: "confirm" }), true), true);
  assert.equal(validatePromptValue("confirm", spec({ kind: "confirm" }), "yes"), false);
  assert.equal(validatePromptValue("input", spec(), "text"), true);
  assert.equal(validatePromptValue("input", spec(), 7), false);

  const choice = spec({ kind: "select", options: ["a", "b"] });
  assert.equal(validatePromptValue("select", choice, "b"), true);
  assert.equal(validatePromptValue("select", choice, "c"), false);
  assert.equal(validatePromptValue("select", { ...choice, allow_free_text: true }, "c"), true);

  const approval = spec({ kind: "approval" });
  assert.equal(validatePromptValue("approval", approval, { choice: "deny", reason: "nope" }), true);
  assert.equal(validatePromptValue("approval", approval, { choice: "deny", reason: undefined }), false);
  assert.equal(validatePromptValue("approval", approval, { choice: "maybe", reason: null }), false);
  assert.equal(validatePromptValue("approval", approval, "allow_once"), false);
});

test("invalid answers leave the prompt open", async () => {
  const book = new PromptBook();
  book.open(spec({ kind: "confirm" }));
  assert.equal(book.answer("p1", "true", "remote"), "invalid_value");
  assert.equal(book.status("p1"), "open");
  assert.deepEqual(book.openPrompts().map((item) => item.prompt_id), ["p1"]);
  const waiting = book.waitFor("p1");
  assert.equal(book.answer("p1", false, "remote"), "answered");
  assert.deepEqual(await waiting, { value: false, source: "remote" });
});

test("cancel and expire settle waiters with null, once each", async () => {
  const book = new PromptBook();
  book.open(spec({ prompt_id: "c1" }));
  book.open(spec({ prompt_id: "c2" }));
  const first = book.waitFor("c1");
  const second = book.waitFor("c2");
  assert.equal(book.cancel("c1"), true);
  assert.equal(book.cancel("c1"), false);
  assert.equal(book.expire("c2"), true);
  assert.equal(book.expire("c2"), false);
  assert.equal(await first, null);
  assert.equal(await second, null);
  assert.equal(book.status("c1"), "cancelled");
  assert.equal(book.status("c2"), "expired");
  assert.deepEqual(book.openPrompts(), []);
});

test("openPrompts keeps open order and drops settled prompts", () => {
  const book = new PromptBook();
  book.open(spec({ prompt_id: "a" }));
  book.open(spec({ prompt_id: "b" }));
  book.open(spec({ prompt_id: "c" }));
  assert.deepEqual(book.openPrompts().map((item) => item.prompt_id), ["a", "b", "c"]);
  book.answer("b", "x", "remote");
  assert.deepEqual(book.openPrompts().map((item) => item.prompt_id), ["a", "c"]);
});

test("opening the same prompt twice keeps the first spec", () => {
  const book = new PromptBook();
  book.open(spec({ prompt_id: "a", title: "first" }));
  book.open(spec({ prompt_id: "a", title: "second" }));
  assert.deepEqual(book.openPrompts().map((item) => item.title), ["first"]);
});

test("waitFor on an unknown or already closed prompt resolves null", async () => {
  const book = new PromptBook();
  assert.equal(await book.waitFor("nope"), null);
  book.open(spec({ prompt_id: "a" }));
  book.cancel("a");
  assert.equal(await book.waitFor("a"), null);
});
