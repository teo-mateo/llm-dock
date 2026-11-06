import { Backoff } from "./backoff.ts";
import type { WireEvent } from "./events.ts";
import { Outbox } from "./outbox.ts";
import { MAX_EVENTS_BATCH, MAX_EVENTS_BODY_BYTES, PATHS, buildEvents, classifyResponse, parseResponse } from "./protocol.ts";
import type { Clock, PresenceLike } from "./presence-types.ts";
import { postJson, type RequestFn } from "./transport.ts";

export type SenderOptions = {
  socketPath: string;
  presence: PresenceLike;
  clock: Clock;
  outbox?: Outbox;
  request?: RequestFn;
  batchSize?: number;
  timeoutMs?: number;
  initialBackoffMs?: number;
  maxBackoffMs?: number;
};

export class EventSender {
  private readonly socketPath: string;
  private readonly presence: PresenceLike;
  private readonly clock: Clock;
  private readonly outbox: Outbox;
  private readonly request: RequestFn;
  private readonly batchSize: number;
  private readonly timeoutMs: number;
  private readonly backoff: Backoff;
  private flushing = false;
  private stopped = false;
  private retryTimer: unknown;
  private inFlight: Promise<void> | null = null;

  constructor(options: SenderOptions) {
    this.socketPath = options.socketPath;
    this.presence = options.presence;
    this.clock = options.clock;
    this.outbox = options.outbox ?? new Outbox(1000, () => options.clock.now());
    this.request = options.request ?? postJson;
    this.batchSize = Math.min(options.batchSize ?? MAX_EVENTS_BATCH, MAX_EVENTS_BATCH);
    this.timeoutMs = options.timeoutMs ?? 3000;
    this.backoff = new Backoff(
      options.initialBackoffMs ?? 1000,
      options.maxBackoffMs ?? 30000,
    );
  }

  enqueue(event: WireEvent): void {
    this.outbox.enqueue(event);
    this.flush();
  }

  start(): void {
    this.stopped = false;
  }

  onOnline(ackedSeq: number): void {
    this.outbox.ack(ackedSeq);
    this.clearRetry();
    this.backoff.reset();
    this.flush();
  }

  async stop(): Promise<void> {
    this.stopped = true;
    this.clearRetry();
    const inFlight = this.inFlight;
    if (inFlight === null) return;
    let timer: unknown;
    const bound = new Promise<void>((resolve) => {
      timer = this.clock.setTimeout(resolve, 1500);
    });
    await Promise.race([inFlight, bound]);
    if (timer !== undefined) this.clock.clearTimeout(timer);
  }

  private flush(): void {
    if (this.stopped || this.flushing || this.retryTimer !== undefined) return;
    const status = this.presence.status();
    if (status.state !== "online" || !status.sessionId || !status.instanceId) return;
    const batch = this.takeBatch(status.sessionId, status.instanceId);
    if (batch.length === 0) return;
    const frame = buildEvents({
      session_id: status.sessionId,
      instance_id: status.instanceId,
      events: batch,
    });
    this.flushing = true;
    const task = this.request(this.socketPath, PATHS.events, frame, this.timeoutMs)
      .then((result) => {
        if (this.stopped) return;
        const kind = classifyResponse(result.status, result.body);
        if (kind === "unknown_session") {
          this.presence.rejoin();
          return;
        }
        if (kind === "bad_frame") {
          this.outbox.discard(batch.map((event) => event.seq));
          this.scheduleRetry();
          return;
        }
        if (kind !== "ok") {
          this.scheduleRetry();
          return;
        }
        const response = parseResponse(result.body);
        const acked = response?.acked_seq;
        if (typeof acked !== "number") {
          this.scheduleRetry();
          return;
        }
        this.outbox.ack(acked);
        this.backoff.reset();
      })
      .catch(() => {
        if (!this.stopped) this.scheduleRetry();
      })
      .finally(() => {
        this.flushing = false;
        if (!this.stopped) this.flush();
      });
    this.inFlight = task;
  }

  private takeBatch(sessionId: string, instanceId: string): WireEvent[] {
    const batch: WireEvent[] = [];
    for (const event of this.outbox.unacked()) {
      if (batch.length >= this.batchSize) break;
      const candidate = [...batch, event];
      const frame = buildEvents({ session_id: sessionId, instance_id: instanceId, events: candidate });
      if (Buffer.byteLength(JSON.stringify(frame)) > MAX_EVENTS_BODY_BYTES) break;
      batch.push(event);
    }
    return batch;
  }

  private scheduleRetry(): void {
    if (this.retryTimer !== undefined) return;
    const delay = this.backoff.next();
    this.retryTimer = this.clock.setTimeout(() => {
      this.retryTimer = undefined;
      if (!this.stopped) this.flush();
    }, delay);
  }

  private clearRetry(): void {
    if (this.retryTimer !== undefined) {
      this.clock.clearTimeout(this.retryTimer);
      this.retryTimer = undefined;
    }
  }
}
