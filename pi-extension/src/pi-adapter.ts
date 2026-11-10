import type { ExtensionContext } from "@earendil-works/pi-coding-agent";

import type { Activity } from "./activity.ts";
import type { HeartbeatSample, HelloFields, SessionReason } from "./protocol.ts";

export type HelloContext = {
  instanceId: string;
  extVersion: string;
  piVersion: string | null;
  previousSessionId: string | null;
  parentSessionId: string | null;
  reason: SessionReason;
};

export function parentSessionIdFrom(env: Record<string, string | undefined>): string | null {
  if (env.PI_SUBAGENT_CHILD !== "1") return null;
  const parent = env.PI_SUBAGENT_PARENT_SESSION?.trim();
  return parent ? parent : null;
}

export function helloFieldsFrom(ctx: ExtensionContext, info: HelloContext): HelloFields {
  return {
    session_id: ctx.sessionManager.getSessionId(),
    instance_id: info.instanceId,
    session_file: ctx.sessionManager.getSessionFile() ?? null,
    cwd: ctx.cwd,
    name: ctx.sessionManager.getSessionName() ?? null,
    pid: process.pid,
    model: ctx.model ? { provider: ctx.model.provider, id: ctx.model.id } : null,
    thinking_level: ctx.thinkingLevel ?? null,
    reason: info.reason,
    previous_session_id: info.previousSessionId,
    parent_session_id: info.parentSessionId,
    pi_version: info.piVersion,
    ext_version: info.extVersion,
  };
}

export function heartbeatSampleFrom(ctx: ExtensionContext, activity: Activity): HeartbeatSample {
  const usage = ctx.getContextUsage();
  return {
    state: activity.working ? "working" : "idle",
    context: usage
      ? { tokens: usage.tokens, window: usage.contextWindow, percent: usage.percent }
      : null,
  };
}
