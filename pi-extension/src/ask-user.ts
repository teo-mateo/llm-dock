import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

import { askUserParameters, askUserSpec, type AskUserParams, type SchemaDsl } from "./ask-user-schema.ts";
import type { PromptAnswer, PromptSpec, PromptSource, PromptValue } from "./prompt-book.ts";
import type { RemotePrompts } from "./remote-prompts.ts";
import type { SessionRuntime } from "./session-runtime.ts";

export type { AskUserKind, AskUserParams, SchemaDsl } from "./ask-user-schema.ts";

export type AskUserOutcome = "answered" | "cancelled" | "expired";

export type AskUserResult = {
  prompt_id: string;
  outcome: AskUserOutcome;
  value: PromptValue | null;
  answered_by: PromptSource | null;
};

export type DialogOptions = { signal?: AbortSignal; timeout?: number };

export type PromptDialogs = {
  confirm(title: string, message: string, options?: DialogOptions): Promise<boolean>;
  select(title: string, options: string[], options?: DialogOptions): Promise<string | undefined>;
  input(title: string, placeholder?: string, options?: DialogOptions): Promise<string | undefined>;
};

export type AskUserDeps = {
  prompts: Pick<RemotePrompts, "open" | "answerTerminal" | "cancel" | "waitFor" | "status">;
  dialogs: PromptDialogs | null;
  hasUI: boolean;
  signal: AbortSignal | undefined;
};

type Winner =
  | { who: "remote"; slot: number; answer: PromptAnswer | null }
  | { who: "terminal"; slot: number; value: PromptValue | null }
  | { who: "aborted"; slot: number };

type Candidate = { slot: number; promise: Promise<Winner> };

function abortRace(
  signal: AbortSignal | undefined,
  slot: number,
): { candidate: Candidate; signal: AbortSignal; dispose: () => void } {
  const controller = new AbortController();
  const forward = () => controller.abort();
  if (signal) {
    if (signal.aborted) forward();
    else signal.addEventListener("abort", forward, { once: true });
  }
  const promise = new Promise<Winner>((resolve) => {
    controller.signal.addEventListener("abort", () => resolve({ who: "aborted", slot }), { once: true });
  });
  return {
    candidate: { slot, promise },
    signal: controller.signal,
    dispose: () => {
      if (signal) signal.removeEventListener("abort", forward);
      controller.abort();
    },
  };
}

function dialogValue(
  deps: AskUserDeps,
  spec: PromptSpec,
  signal: AbortSignal,
): Promise<PromptValue | null> {
  const ui = deps.dialogs as PromptDialogs;
  const options: DialogOptions = { signal, timeout: spec.timeout_ms ?? undefined };
  if (spec.kind === "confirm") return ui.confirm(spec.title, spec.message, options);
  if (spec.kind === "select") return ui.select(spec.title, spec.options, options);
  return ui.input(spec.title, spec.message || "Your answer", options);
}

function toResult(
  spec: PromptSpec,
  outcome: AskUserOutcome,
  value: PromptValue | null = null,
  answeredBy: PromptSource | null = null,
): AskUserResult {
  return { prompt_id: spec.prompt_id, outcome, value, answered_by: answeredBy };
}

function settleClosed(deps: AskUserDeps, spec: PromptSpec): AskUserResult {
  const expired = deps.prompts.status(spec.prompt_id) === "expired";
  return toResult(spec, expired ? "expired" : "cancelled");
}

function settleWinner(
  deps: AskUserDeps,
  spec: PromptSpec,
  winner: Winner,
): AskUserResult | null {
  if (winner.who === "aborted") {
    deps.prompts.cancel(spec.prompt_id);
    return settleClosed(deps, spec);
  }
  if (winner.who === "remote") {
    if (!winner.answer) return settleClosed(deps, spec);
    return toResult(spec, "answered", winner.answer.value, winner.answer.source);
  }
  if (winner.value === null) return null;
  if (deps.prompts.answerTerminal(spec.prompt_id, winner.value) !== "answered") return null;
  return toResult(spec, "answered", winner.value, "terminal");
}

export async function runAskUser(deps: AskUserDeps, spec: PromptSpec): Promise<AskUserResult> {
  deps.prompts.open(spec);
  const race = abortRace(deps.signal, 2);
  const candidates: Candidate[] = [
    {
      slot: 0,
      promise: deps.prompts.waitFor(spec.prompt_id).then((answer) => ({ who: "remote", slot: 0, answer })),
    },
    race.candidate,
  ];
  if (deps.hasUI && deps.dialogs) {
    candidates.push({
      slot: 1,
      promise: dialogValue(deps, spec, race.signal)
        .then((value) => ({ who: "terminal" as const, slot: 1, value }))
        .catch(() => ({ who: "terminal" as const, slot: 1, value: null })),
    });
  }

  try {
    for (;;) {
      const winner = await Promise.race(candidates.map((candidate) => candidate.promise));
      const decided = settleWinner(deps, spec, winner);
      if (decided) return decided;
      const kept = candidates.filter((candidate) => candidate.slot !== winner.slot);
      if (kept.length === 0) return settleClosed(deps, spec);
      candidates.length = 0;
      candidates.push(...kept);
    }
  } finally {
    race.dispose();
  }
}

export function resultText(result: AskUserResult): string {
  if (result.outcome !== "answered") return `no answer (${result.outcome})`;
  const value = typeof result.value === "object" && result.value !== null
    ? JSON.stringify(result.value)
    : String(result.value);
  return `${result.answered_by}: ${value}`;
}

export function registerAskUser(
  pi: ExtensionAPI,
  getRuntime: () => SessionRuntime | undefined,
  Type: SchemaDsl,
): void {
  pi.registerTool({
    name: "ask_user",
    label: "Ask user",
    description: "Ask the operator a question and wait for the answer, either in the terminal "
      + "or from the llm-dock dashboard / phone, whichever replies first.",
    promptSnippet: "Ask the operator a question with ask_user when a decision is theirs to make.",
    promptGuidelines: [
      "Use ask_user when the operator must choose, confirm or supply something you cannot infer.",
      "The answer arrives from the terminal or from the dashboard; never read a timeout or a dismissal as approval.",
    ],
    parameters: askUserParameters(Type),
    exposure: "model-only",
    execute: async (toolCallId, params, signal, _onUpdate, ctx: ExtensionContext) => {
      const runtime = getRuntime();
      if (!runtime) throw new Error("ask_user: no pi-remote session is registered");
      const spec = askUserSpec(toolCallId, params as AskUserParams);
      const result = await runAskUser({
        prompts: runtime.remotePrompts,
        dialogs: ctx.ui,
        hasUI: ctx.hasUI,
        signal,
      }, spec);
      return { content: [{ type: "text", text: resultText(result) }], details: result };
    },
  });
}
