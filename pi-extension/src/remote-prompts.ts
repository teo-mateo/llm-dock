import {
  PromptBook,
  type PromptAnswer,
  type PromptAnswerOutcome,
  type PromptSource,
  type PromptSpec,
  type PromptStatus,
  type PromptValue,
} from "./prompt-book.ts";
import type { CommandHandler } from "./commands.ts";
import type { EventStamper, WireEvent } from "./events.ts";
import { promptClosedBody, promptOpenBody, type PromptCloseReason } from "./prompt-events.ts";
import type { Clock } from "./presence-types.ts";

export type RemotePromptsOptions = {
  stamper: EventStamper;
  emit: (event: WireEvent) => void;
  clock: Clock;
};

export class RemotePrompts {
  private readonly book = new PromptBook();
  private readonly timers = new Map<string, unknown>();
  private readonly stamper: EventStamper;
  private readonly emit: (event: WireEvent) => void;
  private readonly clock: Clock;

  constructor(options: RemotePromptsOptions) {
    this.stamper = options.stamper;
    this.emit = options.emit;
    this.clock = options.clock;
  }

  open(spec: PromptSpec): void {
    this.book.open(spec);
    this.send(promptOpenBody(spec));
    if (spec.timeout_ms === null || spec.timeout_ms <= 0) return;
    const handle = this.clock.setTimeout(() => {
      this.timers.delete(spec.prompt_id);
      this.expire(spec.prompt_id);
    }, spec.timeout_ms);
    this.timers.set(spec.prompt_id, handle);
  }

  answerRemote(promptId: string, value: unknown): PromptAnswerOutcome {
    return this.answer(promptId, value, "remote");
  }

  answerTerminal(promptId: string, value: PromptValue): PromptAnswerOutcome {
    return this.answer(promptId, value, "terminal");
  }

  cancel(promptId: string): boolean {
    return this.close(promptId, "cancelled");
  }

  expire(promptId: string): boolean {
    return this.close(promptId, "expired");
  }

  status(promptId: string): PromptStatus | undefined {
    return this.book.status(promptId);
  }

  openPrompts(): PromptSpec[] {
    return this.book.openPrompts();
  }

  waitFor(promptId: string): Promise<PromptAnswer | null> {
    return this.book.waitFor(promptId);
  }

  replayOpen(): void {
    for (const spec of this.book.openPrompts()) this.send(promptOpenBody(spec));
  }

  private answer(promptId: string, value: unknown, source: PromptSource): PromptAnswerOutcome {
    const outcome = this.book.answer(promptId, value, source);
    if (outcome !== "answered") return outcome;
    this.clearTimer(promptId);
    this.send(promptClosedBody(promptId, "answered", value as PromptValue, source));
    return outcome;
  }

  private close(promptId: string, reason: PromptCloseReason): boolean {
    const closed = reason === "cancelled" ? this.book.cancel(promptId) : this.book.expire(promptId);
    if (!closed) return false;
    this.clearTimer(promptId);
    this.send(promptClosedBody(promptId, reason, null, null));
    return true;
  }

  private clearTimer(promptId: string): void {
    const handle = this.timers.get(promptId);
    if (handle === undefined) return;
    this.timers.delete(promptId);
    this.clock.clearTimeout(handle);
  }

  private send(body: ReturnType<typeof promptOpenBody> | ReturnType<typeof promptClosedBody>): void {
    this.emit(this.stamper.stamp(body));
  }
}

const PROMPT_ERRORS: Record<PromptAnswerOutcome, string | null> = {
  answered: null,
  already_answered: "prompt_already_answered",
  unknown: "prompt_unknown",
  invalid_value: "invalid_value",
};

export function createAnswerPromptHandler(prompts: RemotePrompts): CommandHandler {
  return (args, commandId) => {
    const body = (args ?? {}) as Record<string, unknown>;
    const promptId = typeof body.prompt_id === "string" ? body.prompt_id : "";
    if (!promptId) return { command_id: commandId ?? "answer-invalid", ok: false, error: "invalid_args" };
    const outcome = prompts.answerRemote(promptId, body.value);
    return {
      command_id: commandId ?? promptId,
      ok: outcome === "answered",
      error: PROMPT_ERRORS[outcome],
    };
  };
}
