import { Backoff } from "./backoff.ts";
import { CommandDedupe, dispatch, type CommandHandlers, type CommandResult } from "./commands.ts";
import {
  buildCommandResults,
  buildCommandsPoll,
  classifyResponse,
  MAX_COMMAND_WAIT_MS,
  parseResponse,
  PATHS,
  type Command,
} from "./protocol.ts";
import type { Clock, PresenceLike } from "./presence-types.ts";
import { postJson, type RequestFn } from "./transport.ts";

export type CommandPollerOptions = {
  socketPath: string;
  presence: PresenceLike;
  clock: Clock;
  handlers: CommandHandlers;
  request?: RequestFn;
  waitMs?: number;
  dedupe?: CommandDedupe;
  initialBackoffMs?: number;
  maxBackoffMs?: number;
};

export class CommandPoller {
  private readonly socketPath: string;
  private readonly presence: PresenceLike;
  private readonly clock: Clock;
  private readonly handlers: CommandHandlers;
  private readonly request: RequestFn;
  private readonly waitMs: number;
  private readonly timeoutMs: number;
  private readonly dedupe: CommandDedupe;
  private readonly backoff: Backoff;
  private stopped = false;
  private paused = false;
  private polling = false;
  private timer: unknown;
  private epoch = 0;

  constructor(options: CommandPollerOptions) {
    this.socketPath = options.socketPath;
    this.presence = options.presence;
    this.clock = options.clock;
    this.handlers = options.handlers;
    this.request = options.request ?? postJson;
    this.waitMs = Math.max(0, Math.min(options.waitMs ?? MAX_COMMAND_WAIT_MS, MAX_COMMAND_WAIT_MS));
    this.timeoutMs = this.waitMs + 5000;
    this.dedupe = options.dedupe ?? new CommandDedupe();
    this.backoff = new Backoff(options.initialBackoffMs ?? 1000, options.maxBackoffMs ?? 30000);
  }

  start(): void {
    if (this.stopped) return;
    if (this.paused) {
      this.paused = false;
      this.epoch += 1;
      this.clearTimer();
      this.schedule(0);
      return;
    }
    if (this.polling) return;
    this.clearTimer();
    this.schedule(0);
  }

  pause(): void {
    this.paused = true;
    this.epoch += 1;
    this.clearTimer();
  }

  stop(): void {
    this.stopped = true;
    this.paused = true;
    this.epoch += 1;
    this.clearTimer();
  }

  private schedule(ms: number): void {
    if (this.stopped || this.paused || this.timer !== undefined || this.polling) return;
    this.timer = this.clock.setTimeout(() => {
      this.timer = undefined;
      void this.poll();
    }, ms);
  }

  private clearTimer(): void {
    if (this.timer !== undefined) {
      this.clock.clearTimeout(this.timer);
      this.timer = undefined;
    }
  }

  private requeue(ms: number): void {
    this.polling = false;
    this.schedule(ms);
  }

  private async poll(): Promise<void> {
    if (this.stopped || this.paused) return;
    const epoch = this.epoch;
    const status = this.presence.status();
    if (status.state === "disabled") return;
    if (status.state !== "online" || !status.sessionId || !status.instanceId) {
      this.schedule(this.backoff.next());
      return;
    }
    this.polling = true;
    try {
      const response = await this.request(
        this.socketPath,
        PATHS.commandsPoll,
        buildCommandsPoll({
          session_id: status.sessionId,
          instance_id: status.instanceId,
          wait_ms: this.waitMs,
        }),
        this.timeoutMs,
      );
      if (this.stopped || this.paused || epoch !== this.epoch) return;
      const kind = classifyResponse(response.status, response.body);
      if (kind === "unknown_session") {
        this.presence.rejoin();
        this.requeue(this.backoff.next());
        return;
      }
      if (kind !== "ok") {
        this.requeue(this.backoff.next());
        return;
      }
      this.backoff.reset();
      const parsed = parseResponse(response.body);
      const commands = Array.isArray(parsed?.commands) ? parsed.commands : [];
      if (commands.length === 0) {
        this.requeue(0);
        return;
      }
      const results = await this.execute(commands, epoch);
      if (this.stopped || this.paused || epoch !== this.epoch) return;
      await this.postResults(status, results, epoch);
    } catch {
      if (!this.stopped && !this.paused) this.requeue(this.backoff.next());
    } finally {
      const resumed = !this.stopped && !this.paused && epoch !== this.epoch;
      this.polling = false;
      if (resumed) this.schedule(0);
    }
  }

  private async execute(commands: readonly Command[], epoch: number): Promise<CommandResult[]> {
    const results: CommandResult[] = [];
    for (const command of commands) {
      if (this.stopped || this.paused || epoch !== this.epoch) return results;
      const stored = this.dedupe.seen(command.command_id);
      if (stored) {
        results.push(stored);
        continue;
      }
      const result = await dispatch(command, this.handlers);
      this.dedupe.record(result);
      results.push(result);
    }
    return results;
  }

  private async postResults(
    status: { sessionId: string; instanceId: string },
    results: CommandResult[],
    epoch: number,
  ): Promise<void> {
    const response = await this.request(
      this.socketPath,
      PATHS.commandResults,
      buildCommandResults({
        session_id: status.sessionId,
        instance_id: status.instanceId,
        results,
      }),
      this.timeoutMs,
    );
    if (this.stopped || this.paused || epoch !== this.epoch) return;
    const kind = classifyResponse(response.status, response.body);
    if (kind === "unknown_session") {
      this.presence.rejoin();
      this.requeue(this.backoff.next());
      return;
    }
    if (kind !== "ok") {
      this.requeue(this.backoff.next());
      return;
    }
    this.backoff.reset();
    this.requeue(0);
  }
}
