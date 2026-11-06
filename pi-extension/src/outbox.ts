import { gapEvent, type EventType, type WireEvent } from "./events.ts";

export const DEFAULT_CAPACITY = 1000;

const PROTECTED: ReadonlySet<EventType> = new Set([
  "state",
  "run_end",
  "user_message",
  "assistant_message",
  "gap",
]);

export class Outbox {
  private readonly capacity: number;
  private readonly now: () => number;
  private items: WireEvent[] = [];

  constructor(capacity = DEFAULT_CAPACITY, now: () => number = () => Date.now()) {
    this.capacity = capacity;
    this.now = now;
  }

  enqueue(event: WireEvent): void {
    if (this.dataSize < this.capacity) {
      this.items.push(event);
      return;
    }
    const dropped = this.dropOne();
    if (dropped === null) {
      this.items.push(event);
      return;
    }
    this.recordGapRange(dropped.seq, dropped.seq);
    this.items.push(event);
  }

  discard(seqs: number[]): void {
    const sorted = [...new Set(seqs)].sort((a, b) => a - b);
    if (sorted.length === 0) return;
    const remove = new Set(sorted);
    this.items = this.items.filter((event) => !remove.has(event.seq));
    let runStart = sorted[0];
    let previous = sorted[0];
    for (const seq of sorted.slice(1)) {
      if (seq === previous + 1) {
        previous = seq;
      } else {
        this.recordGapRange(runStart, previous);
        runStart = seq;
        previous = seq;
      }
    }
    this.recordGapRange(runStart, previous);
  }

  ack(seq: number): void {
    this.items = this.items.filter((event) => event.seq > seq);
  }

  unacked(): WireEvent[] {
    return [...this.items].sort((a, b) => a.seq - b.seq);
  }

  get size(): number {
    return this.items.length;
  }

  get dataSize(): number {
    return this.items.filter((event) => event.type !== "gap").length;
  }

  private dropOne(): WireEvent | null {
    let index = this.items.findIndex((event) => event.type === "assistant_delta");
    if (index < 0) index = this.items.findIndex((event) => event.type === "tool_update");
    if (index < 0) {
      index = this.items.findIndex((event) => !PROTECTED.has(event.type));
    }
    if (index < 0) return null;
    return this.items.splice(index, 1)[0];
  }

  private recordGapRange(fromSeq: number, toSeq: number): void {
    this.items.push(gapEvent(fromSeq, this.now(), fromSeq, toSeq));
  }
}
