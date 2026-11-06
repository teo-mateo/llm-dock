import type { AssistantUsage } from "./events.ts";
import type { ModelRef } from "./protocol.ts";

type ContentPart = { type?: string; text?: string; thinking?: string };

export function contentText(message: unknown): string {
  const content = (message as { content?: unknown })?.content;
  if (!Array.isArray(content)) return "";
  return content
    .filter((part) => (part as ContentPart)?.type === "text")
    .map((part) => (part as ContentPart).text ?? "")
    .join("");
}

export function contentThinking(message: unknown): string {
  const content = (message as { content?: unknown })?.content;
  if (!Array.isArray(content)) return "";
  return content
    .filter((part) => (part as ContentPart)?.type === "thinking")
    .map((part) => (part as ContentPart).thinking ?? "")
    .join("");
}

export function isAssistant(message: unknown): boolean {
  return (message as { role?: string })?.role === "assistant";
}

export function userMessageContent(message: unknown): { text: string; imageCount: number } | null {
  if ((message as { role?: string })?.role !== "user") return null;
  const content = (message as { content?: unknown })?.content;
  if (typeof content === "string") return { text: content, imageCount: 0 };
  if (!Array.isArray(content)) return null;
  let text = "";
  let imageCount = 0;
  for (const part of content) {
    const typed = part as { type?: string; text?: string };
    if (typed.type === "text") text += typed.text ?? "";
    else if (typed.type === "image") imageCount += 1;
  }
  return { text, imageCount };
}

export function modelRef(model: unknown): ModelRef | null {
  if (!model || typeof model !== "object") return null;
  const typed = model as { provider?: unknown; id?: unknown };
  if (typeof typed.provider !== "string" || typeof typed.id !== "string") return null;
  return { provider: typed.provider, id: typed.id };
}

export function messageModel(message: unknown): ModelRef | null {
  const typed = message as { provider?: unknown; model?: unknown };
  if (typeof typed.provider !== "string" || typeof typed.model !== "string") return null;
  return { provider: typed.provider, id: typed.model };
}

export function stopReasonOf(message: unknown): string | null {
  const typed = message as { stopReason?: unknown };
  return typeof typed.stopReason === "string" ? typed.stopReason : null;
}

export function usageOf(message: unknown): AssistantUsage | null {
  const usage = (message as { usage?: unknown })?.usage;
  if (!usage || typeof usage !== "object") return null;
  const typed = usage as Record<string, unknown>;
  const cost = typed.cost as Record<string, unknown> | undefined;
  return {
    input: Number(typed.input ?? 0),
    output: Number(typed.output ?? 0),
    cache_read: Number(typed.cacheRead ?? 0),
    cache_write: Number(typed.cacheWrite ?? 0),
    reasoning: typeof typed.reasoning === "number" ? typed.reasoning : null,
    total_tokens: Number(typed.totalTokens ?? 0),
    cost_total: typeof cost?.total === "number" ? cost.total : null,
  };
}
