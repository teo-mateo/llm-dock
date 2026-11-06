export type ContentPart = { type?: string; text?: string };

export function textOfContent(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .map((part) => {
      const typed = part as ContentPart;
      return typeof typed?.text === "string" ? typed.text : "";
    })
    .filter(Boolean)
    .join(" ");
}

export function entryText(entry: unknown): string {
  const typed = entry as { message?: { content?: unknown }; content?: unknown };
  return textOfContent(typed?.message?.content ?? typed?.content);
}

export function findToken(entries: readonly unknown[], token: string): boolean {
  return entries.some((entry) => entryText(entry).includes(token));
}

export function hasToolCalls(message: unknown): boolean {
  const content = (message as { content?: unknown })?.content;
  if (!Array.isArray(content)) return false;
  return content.some((part) => (part as ContentPart)?.type === "toolCall");
}

export function summarizeEntry(entry: unknown): string {
  const typed = entry as { type?: string; message?: { role?: string } };
  const role = typed?.message?.role ?? typed?.type ?? "entry";
  const text = entryText(entry).replace(/\s+/g, " ").trim();
  const preview = text.length > 80 ? `${text.slice(0, 80)}…` : text;
  return `${role}${preview ? ` "${preview}"` : ""}`;
}
