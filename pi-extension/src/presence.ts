import { Backoff } from "./backoff.ts";
import {
  buildBye,
  buildHeartbeat,
  buildHello,
  classifyResponse,
  PATHS,
  type ByeFields,
  type HeartbeatFields,
  type HelloFields,
} from "./protocol.ts";
import {
  resolvePresenceOptions,
  type PresenceOptions,
  type PresenceState,
  type PresenceStatus,
  type ResolvedPresenceOptions,
} from "./presence-types.ts";
import { postJson, type RequestFn } from "./transport.ts";

export class Presence {
  private readonly opts: ResolvedPresenceOptions;
  private readonly request: RequestFn;
  private readonly backoff: Backoff;
  private enabled: boolean;
  private stopped = true;
  private state: PresenceState;
  private sessionId: string | null = null;
  private instanceId: string | null = null;
  private lastHeartbeatAt: number | null = null;
  private nextAttemptAt: number | null = null;
  private offlineNotified = false;
  private retryTimer: unknown;
  private heartbeatTimer: unknown;

  constructor(options: PresenceOptions) {
    this.opts = resolvePresenceOptions(options);
    this.request = options.request ?? postJson;
    this.backoff = new Backoff(this.opts.initialBackoffMs, this.opts.maxBackoffMs);
    this.enabled = options.enabled;
    this.state = this.enabled ? "offline" : "disabled";
  }

  status(): PresenceStatus {
    return {
      state: this.state,
      socketPath: this.opts.socketPath,
      sessionId: this.sessionId,
      instanceId: this.instanceId,
      lastHeartbeatAt: this.lastHeartbeatAt,
      nextAttemptAt: this.nextAttemptAt,
      attempts: this.backoff.attempts,
    };
  }

  start(): void {
    if (!this.enabled) {
      this.setState("disabled");
      return;
    }
    this.stopped = false;
    if (this.state === "online" || this.state === "registering") return;
    this.register();
  }

  async stop(reason: string | null = null): Promise<void> {
    if (this.stopped) return;
    this.stopped = true;
    this.clearRetry();
    this.clearHeartbeat();
    if (this.state === "online" && this.sessionId && this.instanceId) {
      const fields: ByeFields = {
        session_id: this.sessionId,
        instance_id: this.instanceId,
        reason,
      };
      try {
        await this.request(this.opts.socketPath, PATHS.bye, buildBye(fields), this.opts.byeTimeoutMs);
      } catch {
      }
    }
    this.offlineNotified = false;
    this.nextAttemptAt = null;
    this.setState("offline");
  }

  private register(): void {
    this.clearRetry();
    if (this.stopped || !this.enabled) return;
    this.setState("registering");
    let fields: HelloFields;
    try {
      fields = this.opts.helloFields();
    } catch {
      this.fail("hello fields unavailable");
      return;
    }
    this.sessionId = fields.session_id;
    this.instanceId = fields.instance_id;
    this.request(this.opts.socketPath, PATHS.hello, buildHello(fields), this.opts.helloTimeoutMs)
      .then((result) => {
        if (this.stopped) return;
        if (classifyResponse(result.status, result.body) === "ok") {
          this.backoff.reset();
          this.nextAttemptAt = null;
          if (this.offlineNotified) {
            this.opts.notices("pi-remote: dashboard reachable again", "info");
            this.offlineNotified = false;
          }
          this.setState("online");
          this.lastHeartbeatAt = null;
          this.scheduleHeartbeat();
          return;
        }
        this.fail(`hello status ${result.status}`);
      })
      .catch((err: Error) => {
        if (!this.stopped) this.fail(err.message);
      });
  }

  private scheduleHeartbeat(): void {
    this.clearHeartbeat();
    this.heartbeatTimer = this.opts.clock.setTimeout(() => {
      this.heartbeatTimer = undefined;
      void this.tick();
    }, this.opts.heartbeatMs);
  }

  private async tick(): Promise<void> {
    if (this.stopped || this.state !== "online" || !this.sessionId || !this.instanceId) return;
    const sample = this.opts.heartbeatSample();
    const fields: HeartbeatFields = {
      session_id: this.sessionId,
      instance_id: this.instanceId,
      state: sample.state,
      context: sample.context,
      sent_at: this.opts.clock.now(),
    };
    try {
      const result = await this.request(
        this.opts.socketPath,
        PATHS.heartbeat,
        buildHeartbeat(fields),
        this.opts.heartbeatTimeoutMs,
      );
      if (this.stopped) return;
      const kind = classifyResponse(result.status, result.body);
      if (kind === "unknown_session") {
        this.register();
        return;
      }
      if (kind !== "ok") {
        this.fail(`heartbeat status ${result.status}`);
        return;
      }
      this.lastHeartbeatAt = this.opts.clock.now();
      this.scheduleHeartbeat();
    } catch (err) {
      if (!this.stopped) this.fail((err as Error).message);
    }
  }

  private fail(reason: string): void {
    this.clearHeartbeat();
    const delay = this.backoff.next();
    this.nextAttemptAt = this.opts.clock.now() + delay;
    this.setState("offline");
    if (!this.offlineNotified) {
      this.offlineNotified = true;
      this.opts.notices(`pi-remote: dashboard unreachable (${reason}); retrying`, "warning");
    }
    this.retryTimer = this.opts.clock.setTimeout(() => {
      this.retryTimer = undefined;
      if (!this.stopped) this.register();
    }, delay);
  }

  private setState(state: PresenceState): void {
    if (this.state === state) return;
    this.state = state;
    this.opts.stateChanges(state);
  }

  private clearRetry(): void {
    if (this.retryTimer !== undefined) {
      this.opts.clock.clearTimeout(this.retryTimer);
      this.retryTimer = undefined;
    }
  }

  private clearHeartbeat(): void {
    if (this.heartbeatTimer !== undefined) {
      this.opts.clock.clearTimeout(this.heartbeatTimer);
      this.heartbeatTimer = undefined;
    }
  }
}
