import {
  COMMAND_REDELIVERY_MS,
  MAX_COMMAND_WAIT_MS,
  type Command,
  type CommandResult,
} from "../src/protocol.ts";

export const STALE_AFTER_MS = 45000;

export type RegistryLike = Map<string, { lastSeen: number }>;
export type QueuedCommand = { command: Command; handedAt: number | null };

export function commandKey(sessionId: string, instanceId: string): string {
  return `${sessionId}|${instanceId}`;
}

export class FakeCommands {
  readonly queues = new Map<string, QueuedCommand[]>();
  readonly results = new Map<string, CommandResult>();
  private readonly waiters = new Map<string, Set<() => void>>();
  private sequence = 0;

  abortCommand(now = Date.now()): Command {
    this.sequence += 1;
    return { command_id: `abort-${this.sequence}`, kind: "abort", args: {}, issued_at: now };
  }

  enqueue(key: string, command: Command): void {
    const queue = this.queues.get(key) ?? [];
    queue.push({ command, handedAt: null });
    this.queues.set(key, queue);
    this.wake(key);
  }

  recordResult(result: CommandResult): void {
    this.results.set(result.command_id, result);
    for (const [key, queue] of this.queues) {
      const kept = queue.filter((entry) => entry.command.command_id !== result.command_id);
      if (kept.length === 0) this.queues.delete(key);
      else this.queues.set(key, kept);
    }
  }

  available(key: string, now: number): Command[] {
    const queue = this.queues.get(key) ?? [];
    return queue
      .filter((entry) => !this.results.has(entry.command.command_id))
      .filter((entry) => entry.handedAt === null || now - entry.handedAt >= COMMAND_REDELIVERY_MS)
      .map((entry) => entry.command);
  }

  handOut(key: string, commands: Command[], now: number): void {
    const queue = this.queues.get(key) ?? [];
    for (const entry of queue) {
      if (commands.some((command) => command.command_id === entry.command.command_id)) {
        entry.handedAt = now;
      }
    }
  }

  async wait(key: string, ms: number): Promise<void> {
    if (ms <= 0) return;
    await new Promise<void>((resolve) => {
      const timer = setTimeout(() => {
        this.removeWaiter(key, wake);
        resolve();
      }, ms);
      const wake = () => {
        clearTimeout(timer);
        this.removeWaiter(key, wake);
        resolve();
      };
      const set = this.waiters.get(key) ?? new Set<() => void>();
      set.add(wake);
      this.waiters.set(key, set);
    });
  }

  wake(key: string): void {
    const set = this.waiters.get(key);
    if (!set) return;
    for (const wake of set) wake();
  }

  private removeWaiter(key: string, wake: () => void): void {
    const set = this.waiters.get(key);
    if (!set) return;
    set.delete(wake);
    if (set.size === 0) this.waiters.delete(key);
  }
}

function isIds(frame: Record<string, unknown>): { sessionId: string; instanceId: string } | null {
  const sessionId = typeof frame.session_id === "string" ? frame.session_id : "";
  const instanceId = typeof frame.instance_id === "string" ? frame.instance_id : "";
  if (!sessionId || !instanceId) return null;
  return { sessionId, instanceId };
}

export async function handleCommandsPoll(
  frame: Record<string, unknown>,
  registry: RegistryLike,
  commands: FakeCommands,
  now = Date.now(),
  wait: (key: string, ms: number) => Promise<void> = (key, ms) => commands.wait(key, ms),
): Promise<{ status: number; payload: unknown }> {
  if (frame.protocol !== 1) {
    return { status: 400, payload: { ok: false, protocol: 1, error: "unsupported_protocol" } };
  }
  if (frame.type !== "commands_poll") {
    return { status: 400, payload: { ok: false, protocol: 1, error: "bad_frame" } };
  }
  const ids = isIds(frame);
  if (!ids) return { status: 400, payload: { ok: false, protocol: 1, error: "bad_frame" } };
  const waitMs = frame.wait_ms;
  if (typeof waitMs !== "number" || !Number.isInteger(waitMs) || waitMs < 0 || waitMs > MAX_COMMAND_WAIT_MS) {
    return { status: 400, payload: { ok: false, protocol: 1, error: "bad_frame" } };
  }
  const key = commandKey(ids.sessionId, ids.instanceId);
  const entry = registry.get(key);
  if (!entry || now - entry.lastSeen > STALE_AFTER_MS) {
    return { status: 404, payload: { ok: false, protocol: 1, error: "unknown_session" } };
  }
  let effectiveNow = now;
  let delivered = commands.available(key, effectiveNow);
  if (delivered.length === 0 && waitMs > 0) {
    await wait(key, waitMs);
    effectiveNow = Date.now();
    delivered = commands.available(key, effectiveNow);
  }
  commands.handOut(key, delivered, effectiveNow);
  return { status: 200, payload: { ok: true, protocol: 1, commands: delivered } };
}

export function handleCommandResults(
  frame: Record<string, unknown>,
  registry: RegistryLike,
  commands: FakeCommands,
  now = Date.now(),
): { status: number; payload: unknown } {
  if (frame.protocol !== 1) {
    return { status: 400, payload: { ok: false, protocol: 1, error: "unsupported_protocol" } };
  }
  if (frame.type !== "command_results") {
    return { status: 400, payload: { ok: false, protocol: 1, error: "bad_frame" } };
  }
  const ids = isIds(frame);
  if (!ids) return { status: 400, payload: { ok: false, protocol: 1, error: "bad_frame" } };
  const results = frame.results;
  if (!Array.isArray(results)) {
    return { status: 400, payload: { ok: false, protocol: 1, error: "bad_frame" } };
  }
  const valid = results.every((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return false;
    const result = item as Record<string, unknown>;
    return typeof result.command_id === "string"
      && result.command_id.length > 0
      && typeof result.ok === "boolean"
      && (result.error === null || typeof result.error === "string");
  });
  if (!valid) return { status: 400, payload: { ok: false, protocol: 1, error: "bad_frame" } };
  const key = commandKey(ids.sessionId, ids.instanceId);
  const entry = registry.get(key);
  if (!entry || now - entry.lastSeen > STALE_AFTER_MS) {
    return { status: 404, payload: { ok: false, protocol: 1, error: "unknown_session" } };
  }
  for (const result of results as CommandResult[]) commands.recordResult(result);
  return { status: 200, payload: { ok: true, protocol: 1 } };
}
