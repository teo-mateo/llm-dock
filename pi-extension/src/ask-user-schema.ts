import type { PromptKind, PromptSpec } from "./prompt-book.ts";

export type AskUserKind = Extract<PromptKind, "confirm" | "select" | "input">;

export type AskUserParams = {
  question: string;
  message?: string;
  kind?: AskUserKind;
  options?: string[];
  allow_free_text?: boolean;
  timeout_ms?: number;
};

export type SchemaDsl = {
  String: () => object;
  Boolean: () => object;
  Number: () => object;
  Optional: (schema: object) => object;
  Array: (schema: object) => object;
  Union: (schemas: object[]) => object;
  Literal: (value: string) => object;
  Object: (properties: Record<string, object>) => object;
};

const KINDS: readonly AskUserKind[] = ["confirm", "select", "input"];

export function askUserParameters(Type: SchemaDsl): object {
  return Type.Object({
    question: Type.String(),
    message: Type.Optional(Type.String()),
    kind: Type.Optional(
      Type.Union([Type.Literal("confirm"), Type.Literal("select"), Type.Literal("input")]),
    ),
    options: Type.Optional(Type.Array(Type.String())),
    allow_free_text: Type.Optional(Type.Boolean()),
    timeout_ms: Type.Optional(Type.Number()),
  });
}

export function askUserSpec(promptId: string, params: AskUserParams): PromptSpec {
  const kind = params.kind ?? "input";
  if (!KINDS.includes(kind)) throw new Error(`ask_user: unsupported kind ${String(params.kind)}`);
  const options = params.options ?? [];
  if (kind === "select" && options.length === 0) {
    throw new Error("ask_user: kind \"select\" requires a non-empty options array");
  }
  return {
    prompt_id: promptId,
    kind,
    title: params.question,
    message: params.message ?? "",
    options,
    allow_free_text: params.allow_free_text ?? false,
    timeout_ms: params.timeout_ms ?? null,
  };
}
