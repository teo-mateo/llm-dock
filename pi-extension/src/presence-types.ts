import type { HeartbeatFields, HelloFields } from "./protocol.ts";
import type { RequestFn } from "./transport.ts";

export type PresenceState = "disabled" | "offline" | "registering" | "online";

export type Clock = {
  now: () => number;
  setTimeout: (fn: () => void, ms: number) => unknown;
  clearTimeout: (handle: unknown) => void;
};

export type HeartbeatSample = Pick<HeartbeatFields, "state" | "context">;

export type PresenceOptions = {
  socketPath: string;
  enabled: boolean;
  clock: Clock;
  helloFields: () => HelloFields;
  heartbeatSample: () => HeartbeatSample;
  request?: RequestFn;
  heartbeatMs?: number;
  helloTimeoutMs?: number;
  heartbeatTimeoutMs?: number;
  byeTimeoutMs?: number;
  initialBackoffMs?: number;
  maxBackoffMs?: number;
  onNotice?: (message: string, level: "info" | "warning") => void;
  onStateChange?: (state: PresenceState) => void;
  onOnline?: (ackedSeq: number) => void;
};

export type ResolvedPresenceOptions = {
  socketPath: string;
  clock: Clock;
  helloFields: () => HelloFields;
  heartbeatSample: () => HeartbeatSample;
  notices: (message: string, level: "info" | "warning") => void;
  stateChanges: (state: PresenceState) => void;
  onOnline: (ackedSeq: number) => void;
  heartbeatMs: number;
  helloTimeoutMs: number;
  heartbeatTimeoutMs: number;
  byeTimeoutMs: number;
  initialBackoffMs: number;
  maxBackoffMs: number;
};

export type PresenceLike = {
  status: () => PresenceStatus;
  rejoin: () => void;
};

export type PresenceStatus = {
  state: PresenceState;
  socketPath: string;
  sessionId: string | null;
  instanceId: string | null;
  lastHeartbeatAt: number | null;
  nextAttemptAt: number | null;
  attempts: number;
};

export function resolvePresenceOptions(options: PresenceOptions): ResolvedPresenceOptions {
  return {
    socketPath: options.socketPath,
    clock: options.clock,
    helloFields: options.helloFields,
    heartbeatSample: options.heartbeatSample,
    notices: options.onNotice ?? (() => {}),
    stateChanges: options.onStateChange ?? (() => {}),
    onOnline: options.onOnline ?? (() => {}),
    heartbeatMs: options.heartbeatMs ?? 15000,
    helloTimeoutMs: options.helloTimeoutMs ?? 3000,
    heartbeatTimeoutMs: options.heartbeatTimeoutMs ?? 2000,
    byeTimeoutMs: options.byeTimeoutMs ?? 1000,
    initialBackoffMs: options.initialBackoffMs ?? 1000,
    maxBackoffMs: options.maxBackoffMs ?? 30000,
  };
}
