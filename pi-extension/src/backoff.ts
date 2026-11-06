export class Backoff {
  private readonly initialMs: number;
  private readonly maxMs: number;
  attempts = 0;

  constructor(initialMs = 1000, maxMs = 30000) {
    this.initialMs = initialMs;
    this.maxMs = maxMs;
  }

  next(): number {
    this.attempts += 1;
    return Math.min(this.initialMs * 2 ** (this.attempts - 1), this.maxMs);
  }

  reset(): void {
    this.attempts = 0;
  }
}
