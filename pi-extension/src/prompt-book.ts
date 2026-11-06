export type PromptKind = "confirm" | "select" | "input" | "approval";
export type PromptChoice = "allow_once" | "allow_session" | "deny";
export type PromptApproval = { choice: PromptChoice; reason: string | null };
export type PromptValue = boolean | string | PromptApproval;
export type PromptSource = "terminal" | "remote";
export type PromptStatus = "open" | "answered" | "cancelled" | "expired";
export type PromptAnswerOutcome = "answered" | "already_answered" | "unknown" | "invalid_value";

export type PromptSpec = {
  prompt_id: string;
  kind: PromptKind;
  title: string;
  message: string;
  options: string[];
  allow_free_text: boolean;
  timeout_ms: number | null;
};

export type PromptAnswer = { value: PromptValue; source: PromptSource };

const CHOICES: readonly string[] = ["allow_once", "allow_session", "deny"];

export function isPromptApproval(value: unknown): value is PromptApproval {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  return CHOICES.includes(record.choice as string)
    && (record.reason === null || typeof record.reason === "string");
}

export function validatePromptValue(
  kind: PromptKind, spec: PromptSpec, value: unknown,
): value is PromptValue {
  if (kind === "confirm") return typeof value === "boolean";
  if (kind === "input") return typeof value === "string";
  if (kind === "select") {
    if (typeof value !== "string") return false;
    return spec.options.includes(value) || spec.allow_free_text;
  }
  return isPromptApproval(value);
}

type Entry = {
  spec: PromptSpec;
  status: PromptStatus;
  answer: PromptAnswer | null;
  waiters: Set<(answer: PromptAnswer | null) => void>;
};

export class PromptBook {
  private readonly entries = new Map<string, Entry>();

  open(spec: PromptSpec): void {
    if (this.entries.has(spec.prompt_id)) return;
    this.entries.set(spec.prompt_id, {
      spec: { ...spec, options: [...spec.options] },
      status: "open",
      answer: null,
      waiters: new Set(),
    });
  }

  status(promptId: string): PromptStatus | undefined {
    return this.entries.get(promptId)?.status;
  }

  openPrompts(): PromptSpec[] {
    const open: PromptSpec[] = [];
    for (const entry of this.entries.values()) {
      if (entry.status === "open") open.push(entry.spec);
    }
    return open;
  }

  answer(promptId: string, value: unknown, source: PromptSource): PromptAnswerOutcome {
    const entry = this.entries.get(promptId);
    if (!entry) return "unknown";
    if (entry.status !== "open") return "already_answered";
    if (!validatePromptValue(entry.spec.kind, entry.spec, value)) return "invalid_value";
    entry.status = "answered";
    entry.answer = { value, source };
    this.settle(entry);
    return "answered";
  }

  cancel(promptId: string): boolean {
    return this.closePrompt(promptId, "cancelled");
  }

  expire(promptId: string): boolean {
    return this.closePrompt(promptId, "expired");
  }

  waitFor(promptId: string): Promise<PromptAnswer | null> {
    const entry = this.entries.get(promptId);
    if (!entry) return Promise.resolve(null);
    if (entry.status === "answered") return Promise.resolve(entry.answer);
    if (entry.status !== "open") return Promise.resolve(null);
    return new Promise((resolve) => {
      const waiter = (answer: PromptAnswer | null): void => {
        entry.waiters.delete(waiter);
        resolve(answer);
      };
      entry.waiters.add(waiter);
    });
  }

  private closePrompt(promptId: string, status: PromptStatus): boolean {
    const entry = this.entries.get(promptId);
    if (!entry || entry.status !== "open") return false;
    entry.status = status;
    this.settle(entry);
    return true;
  }

  private settle(entry: Entry): void {
    const waiters = [...entry.waiters];
    entry.waiters.clear();
    for (const waiter of waiters) waiter(entry.answer);
  }
}
