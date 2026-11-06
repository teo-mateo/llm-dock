export const DELTA_INTERVAL_MS = 100;
export const DELTA_MAX_CHARS = 2000;
export const TOOL_UPDATE_INTERVAL_MS = 250;
export const MAX_TOOL_TEXT_BYTES = 64 * 1024;

export type DeltaChunk = { text: string; thinking: string };
export type ToolText = { text: string | null; truncated: boolean };

export class DeltaCoalescer {
  private text = "";
  private thinking = "";
  private hasPending = false;
  private lastFlushAt = 0;

  addText(delta: string, now: number): DeltaChunk[] {
    const out: DeltaChunk[] = [];
    const due = this.flushIfDue(now);
    if (due) out.push(due);
    if (!this.hasPending) this.lastFlushAt = now;
    this.text += delta;
    this.hasPending = true;
    if (this.text.length + this.thinking.length >= DELTA_MAX_CHARS) {
      out.push(this.take(now));
    }
    return out;
  }

  addThinking(delta: string, now: number): DeltaChunk[] {
    const out: DeltaChunk[] = [];
    const due = this.flushIfDue(now);
    if (due) out.push(due);
    if (!this.hasPending) this.lastFlushAt = now;
    this.thinking += delta;
    this.hasPending = true;
    if (this.text.length + this.thinking.length >= DELTA_MAX_CHARS) {
      out.push(this.take(now));
    }
    return out;
  }

  flush(now: number): DeltaChunk[] {
    if (!this.hasPending) return [];
    return [this.take(now)];
  }

  private flushIfDue(now: number): DeltaChunk | null {
    if (!this.hasPending) return null;
    if (now - this.lastFlushAt < DELTA_INTERVAL_MS) return null;
    return this.take(now);
  }

  private take(now: number): DeltaChunk {
    const chunk = { text: this.text, thinking: this.thinking };
    this.text = "";
    this.thinking = "";
    this.hasPending = false;
    this.lastFlushAt = now;
    return chunk;
  }
}

export class ToolThrottle {
  private readonly lastEmitted = new Map<string, number>();

  allow(callId: string, now: number): boolean {
    const last = this.lastEmitted.get(callId);
    if (last !== undefined && now - last < TOOL_UPDATE_INTERVAL_MS) return false;
    this.lastEmitted.set(callId, now);
    return true;
  }

  done(callId: string): void {
    this.lastEmitted.delete(callId);
  }
}

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
