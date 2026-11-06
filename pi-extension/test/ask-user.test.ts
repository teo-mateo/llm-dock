import { test } from "node:test";
import assert from "node:assert/strict";

import { registerAskUser, resultText, runAskUser, type PromptDialogs } from "../src/ask-user.ts";
import { askUserSpec } from "../src/ask-user-schema.ts";
import { EventStamper } from "../src/events.ts";
import { RemotePrompts } from "../src/remote-prompts.ts";
import { fakeClock, flush } from "./fake-clock.ts";

const Type = {
  String: () => ({ type: "string" }),
  Boolean: () => ({ type: "boolean" }),
  Number: () => ({ type: "number" }),
  Optional: (schema: object) => ({ optional: true, schema }),
  Array: (schema: object) => ({ type: "array", items: schema }),
  Union: (schemas: object[]) => ({ anyOf: schemas }),
  Literal: (value: string) => ({ const: value }),
  Object: (properties: Record<string, object>) => ({ type: "object", properties }),
};

type Tool = {
  name: string;
  label: string;
  description: string;
  promptGuidelines?: string[];
  promptSnippet?: string;
  parameters: Record<string, any>;
  exposure: string;
  execute: (id: string, params: unknown, signal: AbortSignal | undefined, onUpdate: undefined, ctx: unknown) => Promise<{ content: { text: string }[]; details: Record<string, unknown> }>;
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

function harness() {
  const clock = fakeClock(0);
  const emitted: Record<string, any>[] = [];
  const prompts = new RemotePrompts({
    stamper: new EventStamper(clock),
    emit: (event) => emitted.push(event as unknown as Record<string, any>),
    clock,
  });
  const registered: Tool[] = [];
  const pi = { registerTool: (tool: Tool) => registered.push(tool) } as any;
  const runtime = { remotePrompts: prompts } as any;
  registerAskUser(pi, () => runtime, Type as any);
  const tool = registered[0];
  const of = (type: string) => emitted.filter((event) => event.type === type);
  return { clock, emitted, prompts, tool, of };
}

function dialogs(stubs: Partial<PromptDialogs> & { calls?: string[] } = {}): PromptDialogs {
  const calls = stubs.calls ?? [];
  const wrap = <T>(name: string, fn: (...args: unknown[]) => Promise<T>) =>
    async (...args: unknown[]): Promise<T> => {
      calls.push(name);
      return fn(...args);
    };
  return {
    confirm: wrap("confirm", stubs.confirm ?? (() => Promise.resolve(false))),
    select: wrap("select", stubs.select ?? (() => Promise.resolve(undefined))),
    input: wrap("input", stubs.input ?? (() => Promise.resolve(undefined))),
  };
}

const ctx = (ui: PromptDialogs, hasUI = true) => ({ ui, hasUI }) as any;

test("the tool is registered as a model-only prompt with a label", () => {
  const { tool } = harness();
  assert.equal(tool.name, "ask_user");
  assert.equal(tool.label, "Ask user");
  assert.equal(tool.exposure, "model-only");
  assert.ok(tool.description.length > 20);
  assert.equal(tool.promptGuidelines?.length, 2);
  assert.equal(typeof tool.promptSnippet, "string");
  assert.equal(tool.parameters.type, "object");
  assert.deepEqual(Object.keys(tool.parameters.properties), [
    "question", "message", "kind", "options", "allow_free_text", "timeout_ms",
  ]);
  assert.deepEqual(tool.parameters.properties.kind.schema.anyOf, [
    { const: "confirm" }, { const: "select" }, { const: "input" },
  ]);
});

test("prompt_id is the tool call id", async () => {
  const { tool, prompts, of } = harness();
  const running = tool.execute("call-42", { question: "Which port" }, undefined, undefined,
    ctx(dialogs(), false));
  await flush();
  assert.equal(of("prompt_open")[0].prompt_id, "call-42");
  prompts.answerRemote("call-42", "3301");
  const result = await running;
  assert.equal(result.details.prompt_id, "call-42");
  assert.deepEqual(of("prompt_closed")[0].prompt_id, "call-42");
});

test("kind defaults to input and options are kept", async () => {
  const { tool, prompts, of } = harness();
  const running = tool.execute("call-1", { question: "Which", options: ["a"] }, undefined, undefined,
    ctx(dialogs(), false));
  await flush();
  const open = of("prompt_open")[0];
  assert.equal(open.kind, "input");
  assert.deepEqual(open.options, ["a"]);
  assert.equal(open.title, "Which");
  assert.equal(open.timeout_ms, null);
  prompts.answerRemote("call-1", "x");
  await running;
});

test("the terminal dialog wins when it answers first", async () => {
  const { tool, prompts, emitted, of } = harness();
  const ui = dialogs({ input: () => Promise.resolve("typed in the terminal") });
  const result = await tool.execute("call-2", { question: "Which" }, undefined, undefined, ctx(ui));
  assert.deepEqual(result.details, {
    prompt_id: "call-2", outcome: "answered", value: "typed in the terminal", answered_by: "terminal",
  });
  assert.equal(prompts.status("call-2"), "answered");
  assert.deepEqual(of("prompt_closed")[0].answered_by, "terminal");
  assert.equal(emitted.length, 2);
});

test("a confirm answer reaches the model as a boolean", async () => {
  const { tool } = harness();
  const ui = dialogs({ confirm: () => Promise.resolve(true) });
  const result = await tool.execute("call-3", { question: "Deploy", kind: "confirm" }, undefined, undefined, ctx(ui));
  assert.equal(result.details.value, true);
  assert.equal(result.content[0].text, "terminal: true");
});

test("the remote answer wins when the dialog is still open", async () => {
  const { tool, prompts, of } = harness();
  const answer = deferred<string | undefined>();
  const result = tool.execute("call-4", { question: "Which" }, undefined, undefined,
    ctx(dialogs({ input: () => answer.promise })));
  await flush();
  prompts.answerRemote("call-4", "from the phone");
  const settled = await result;
  assert.deepEqual(settled.details, {
    prompt_id: "call-4", outcome: "answered", value: "from the phone", answered_by: "remote",
  });
  assert.equal(of("prompt_closed")[0].answered_by, "remote");
});

test("a dismissed dialog keeps the prompt open for the remote answer", async () => {
  const { tool, prompts } = harness();
  const calls: string[] = [];
  const running = tool.execute("call-5", { question: "Which" }, undefined, undefined,
    ctx(dialogs({ calls, input: () => Promise.resolve(undefined) })));
  await flush();
  assert.deepEqual(calls, ["input"]);
  assert.equal(prompts.status("call-5"), "open");
  prompts.answerRemote("call-5", "late answer");
  assert.equal((await running).details.value, "late answer");
});

test("without UI no dialog is opened and only the remote answer counts", async () => {
  const { tool, prompts } = harness();
  const calls: string[] = [];
  const running = tool.execute("call-6", { question: "Which" }, undefined, undefined,
    ctx(dialogs({ calls }), false));
  await flush();
  assert.deepEqual(calls, []);
  prompts.answerRemote("call-6", "remote only");
  assert.equal((await running).details.answered_by, "remote");
});

test("an aborted tool call cancels the prompt", async () => {
  const { tool, prompts, of } = harness();
  const controller = new AbortController();
  const running = tool.execute("call-7", { question: "Which" }, controller.signal, undefined,
    ctx(dialogs(), false));
  await flush();
  controller.abort();
  const result = await running;
  assert.deepEqual(result.details, {
    prompt_id: "call-7", outcome: "cancelled", value: null, answered_by: null,
  });
  assert.equal(prompts.status("call-7"), "cancelled");
  assert.equal(of("prompt_closed")[0].reason, "cancelled");
});

test("a select call without options is refused", () => {
  assert.throws(() => askUserSpec("c", { question: "Which", kind: "select" }), /non-empty options/);
});

test("an expired prompt reports expired", async () => {
  const { clock, prompts, tool } = harness();
  const running = tool.execute("call-8", { question: "Which", timeout_ms: 1000 }, undefined, undefined,
    ctx(dialogs(), false));
  await flush();
  await clock.advance(1000);
  await flush();
  assert.equal((await running).details.outcome, "expired");
});

test("runAskUser answers an approval prompt that arrives remotely", async () => {
  const { prompts } = harness();
  const spec = askUserSpec("call-9", { question: "Allow rm" });
  const running = runAskUser({ prompts, dialogs: null, hasUI: false, signal: undefined }, {
    ...spec, kind: "approval",
  });
  await flush();
  prompts.answerRemote("call-9", { choice: "allow_once", reason: null });
  assert.deepEqual((await running).value, { choice: "allow_once", reason: null });
});

test("resultText renders every outcome for the model", () => {
  assert.equal(resultText({ prompt_id: "c", outcome: "cancelled", value: null, answered_by: null }),
    "no answer (cancelled)");
  assert.equal(resultText({ prompt_id: "c", outcome: "expired", value: null, answered_by: null }),
    "no answer (expired)");
  assert.equal(resultText({ prompt_id: "c", outcome: "answered", value: false, answered_by: "terminal" }),
    "terminal: false");
  assert.equal(resultText({ prompt_id: "c", outcome: "answered", value: "a", answered_by: "remote" }),
    "remote: a");
  assert.equal(
    resultText({
      prompt_id: "c", outcome: "answered", value: { choice: "deny", reason: "no" }, answered_by: "remote",
    }),
    'remote: {"choice":"deny","reason":"no"}',
  );
});

test("with no session registered the tool fails instead of hanging", async () => {
  const registered: Tool[] = [];
  registerAskUser({ registerTool: (tool: Tool) => registered.push(tool) } as any, () => undefined, Type as any);
  await assert.rejects(
    () => registered[0].execute("call-x", { question: "Which" }, undefined, undefined, ctx(dialogs(), false)),
    /no pi-remote session/,
  );
});

test("a remote answer dismisses the dialog left open in the terminal", async () => {
  const { tool, prompts } = harness();
  let seen: AbortSignal | undefined;
  const hanging = (_title: string, _args: unknown, options?: { signal?: AbortSignal }) => {
    seen = options?.signal;
    return new Promise<string | undefined>(() => {});
  };
  const running = tool.execute("call-10", { question: "Which" }, undefined, undefined,
    ctx({ confirm: () => Promise.resolve(false), select: () => Promise.resolve(undefined), input: hanging }));
  await flush();
  prompts.answerRemote("call-10", "red");
  const result = await running;
  assert.equal(result.details.answered_by, "remote");
  assert.equal(seen?.aborted, true);
});

test("aborting the tool call dismisses the dialog through the same signal", async () => {
  const { tool, prompts } = harness();
  const controller = new AbortController();
  let seen: AbortSignal | undefined;
  const hanging = (_title: string, _args: unknown, options?: { signal?: AbortSignal }) => {
    seen = options?.signal;
    return new Promise<string | undefined>(() => {});
  };
  const running = tool.execute("call-11", { question: "Which" }, controller.signal, undefined,
    ctx({ confirm: () => Promise.resolve(false), select: () => Promise.resolve(undefined), input: hanging }));
  await flush();
  assert.equal(seen?.aborted, false);
  controller.abort();
  assert.equal((await running).details.outcome, "cancelled");
  assert.equal(prompts.status("call-11"), "cancelled");
  assert.equal(seen?.aborted, true);
});
