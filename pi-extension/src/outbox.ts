import { gapEvent, type GapEvent, type WireEvent } from "./events.ts";

export const DEFAULT_CAPACITY = 1000;

const PROTECTED = new Set<string>([
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
    this.recordGap(dropped);
    this.items.push(event);
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
    if (index < 0) index = this.items.findIndex((event) => !PROTECTED.has(event.type));
    if (index < 0) return null;
    return this.items.splice(index, 1)[0];
  }

  private recordGap(dropped: WireEvent): void {
    const gaps = this.items.filter((event): event is GapEvent => event.type === "gap");
    const covering = gaps.find(
      (gap) => dropped.seq >= gap.from_seq && dropped.seq <= gap.to_seq,
    );
    if (covering) return;
    const adjacent = gaps.find(
      (gap) => gap.to_seq + 1 === dropped.seq || dropped.seq + 1 === gap.from_seq,
    );
    if (adjacent) {
      const from = Math.min(adjacent.from_seq, dropped.seq);
      const to = Math.max(adjacent.to_seq, dropped.seq);
      const replacement = gapEvent(adjacent.seq, this.now(), from, to);
      this.items[this.items.indexOf(adjacent)] = replacement;
      return;
    }
    this.items.push(gapEvent(dropped.seq, this.now(), dropped.seq, dropped.seq));
  }
}
