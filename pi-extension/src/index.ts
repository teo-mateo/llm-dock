import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";

import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

import { detectPiVersion, loadConfig } from "./config.ts";
import { Presence, type PresenceStatus } from "./presence.ts";
import type { SessionReason } from "./protocol.ts";
import { sessionIdFromFile } from "./session.ts";

function readExtVersion(): string {
  try {
    const url = new URL("../package.json", import.meta.url);
    const parsed = JSON.parse(readFileSync(url, "utf8"));
    return typeof parsed.version === "string" ? parsed.version : "0.0.0";
  } catch {
    return "0.0.0";
  }
}

function statusText(status: PresenceStatus): string {
  const last = status.lastHeartbeatAt ? new Date(status.lastHeartbeatAt).toISOString() : "never";
  const next = status.nextAttemptAt ? new Date(status.nextAttemptAt).toISOString() : "-";
  const session = status.sessionId ?? "-";
  return `pi-remote: ${status.state} · socket ${status.socketPath} · session ${session} · last heartbeat ${last} · next attempt ${next}`;
}

export default function (pi: ExtensionAPI) {
  const config = loadConfig();
  const instanceId = randomUUID();
  const extVersion = readExtVersion();
  const piVersion = detectPiVersion();

  let presence: Presence | undefined;
  let working = false;
  let previousSessionId: string | null = null;

  function createPresence(ctx: ExtensionContext, reason: SessionReason): Presence {
    return new Presence({
      socketPath: config.socketPath,
      enabled: config.enabled,
      clock: {
        now: () => Date.now(),
        setTimeout: (fn, ms) => setTimeout(fn, ms),
        clearTimeout: (handle) => clearTimeout(handle as NodeJS.Timeout),
      },
      helloFields: () => ({
        session_id: ctx.sessionManager.getSessionId(),
        instance_id: instanceId,
        session_file: ctx.sessionManager.getSessionFile() ?? null,
        cwd: ctx.cwd,
        name: ctx.sessionManager.getSessionName() ?? null,
        pid: process.pid,
        model: ctx.model ? { provider: ctx.model.provider, id: ctx.model.id } : null,
        thinking_level: ctx.thinkingLevel ?? null,
        reason,
        previous_session_id: previousSessionId,
        pi_version: piVersion,
        ext_version: extVersion,
      }),
      heartbeatSample: () => {
        const usage = ctx.getContextUsage();
        return {
          state: working ? "working" : "idle",
          context: usage
            ? { tokens: usage.tokens, window: usage.contextWindow, percent: usage.percent }
            : null,
        };
      },
      onNotice: (message, level) => ctx.ui.notify(message, level),
    });
  }

  pi.on("session_start", async (event, ctx) => {
    working = false;
    previousSessionId = sessionIdFromFile(event.previousSessionFile);
    if (presence) void presence.stop("switch");
    presence = createPresence(ctx, event.reason);
    presence.start();
  });

  pi.on("session_shutdown", async () => {
    if (presence) {
      await presence.stop("shutdown");
      presence = undefined;
    }
  });

  pi.on("agent_start", async () => {
    working = true;
  });

  pi.on("agent_settled", async () => {
    working = false;
  });

  pi.registerCommand("remote", {
    description: "Show or change pi-remote registration: /remote [status|on|off]",
    handler: async (args, ctx) => {
      const action = args.trim() || "status";
      if (!presence) {
        ctx.ui.notify("pi-remote: no session registration", "warning");
        return;
      }
      if (action === "off") {
        await presence.stop("remote_off");
        ctx.ui.notify("pi-remote: off", "info");
        return;
      }
      if (action === "on") {
        if (!config.enabled) {
          ctx.ui.notify("pi-remote: disabled by config (PI_REMOTE / pi-remote.json)", "warning");
          return;
        }
        presence.start();
        ctx.ui.notify("pi-remote: on", "info");
        return;
      }
      if (action !== "status") {
        ctx.ui.notify("usage: /remote [status|on|off]", "warning");
        return;
      }
      const status = presence.status();
      ctx.ui.notify(statusText(status), status.state === "online" ? "info" : "warning");
    },
  });
}
