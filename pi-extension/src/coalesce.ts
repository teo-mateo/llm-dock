export const DELTA_INTERVAL_MS = 100;
export const DELTA_MAX_CHARS = 2000;

export type DeltaChunk = { text: string; thinking: string };

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
