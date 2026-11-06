import type { PresenceStatus } from "./presence-types.ts";

export type RemoteAction = "status" | "on" | "off" | "invalid";

export function parseRemoteAction(args: string): RemoteAction {
  const value = args.trim();
  if (value === "" || value === "status") return "status";
  if (value === "on") return "on";
  if (value === "off") return "off";
  return "invalid";
}

export function statusText(status: PresenceStatus): string {
  const last = status.lastHeartbeatAt ? new Date(status.lastHeartbeatAt).toISOString() : "never";
  const next = status.nextAttemptAt ? new Date(status.nextAttemptAt).toISOString() : "-";
  const session = status.sessionId ?? "-";
  return `pi-remote: ${status.state} · socket ${status.socketPath} · session ${session} · last heartbeat ${last} · next attempt ${next}`;
}
