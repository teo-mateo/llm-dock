export const MAX_TOOL_TEXT_BYTES = 64 * 1024;

export type ToolText = { text: string | null; truncated: boolean };

export function toolText(value: unknown): ToolText {
  if (value === undefined) return { text: null, truncated: false };
  let raw: string;
  if (typeof value === "string") {
    raw = value;
  } else {
    try {
      const json = JSON.stringify(value);
      raw = json === undefined ? String(value) : json;
    } catch {
      raw = String(value);
    }
  }
  if (Buffer.byteLength(raw) <= MAX_TOOL_TEXT_BYTES) {
    return { text: raw, truncated: false };
  }
  let out = "";
  let bytes = 0;
  for (const char of raw) {
    const size = Buffer.byteLength(char);
    if (bytes + size > MAX_TOOL_TEXT_BYTES) break;
    out += char;
    bytes += size;
  }
  return { text: out, truncated: true };
}
