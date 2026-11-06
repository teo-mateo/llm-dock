import { randomUUID } from "node:crypto";

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

import { createActivity } from "./activity.ts";
import { detectPiVersion, loadConfig, readExtVersion } from "./config.ts";
import { heartbeatSampleFrom, helloFieldsFrom } from "./pi-adapter.ts";
import { Presence } from "./presence.ts";
import { parseRemoteAction, statusText } from "./remote-command.ts";
import { sessionIdFromFile } from "./session.ts";

export default function (pi: ExtensionAPI) {
  const config = loadConfig();
  const instanceId = randomUUID();
  const extVersion = readExtVersion(new URL("../package.json", import.meta.url));
  const piVersion = detectPiVersion();
  const activity = createActivity();

  let presence: Presence | undefined;
  let previousSessionId: string | null = null;

  pi.on("session_start", async (event, ctx) => {
    activity.working = false;
    previousSessionId = sessionIdFromFile(event.previousSessionFile);
    if (presence) void presence.stop("switch");
    presence = new Presence({
      socketPath: config.socketPath,
      enabled: config.enabled,
      clock: {
        now: () => Date.now(),
        setTimeout: (fn, ms) => setTimeout(fn, ms),
        clearTimeout: (handle) => clearTimeout(handle as NodeJS.Timeout),
      },
      helloFields: () =>
        helloFieldsFrom(ctx, {
          instanceId,
          extVersion,
          piVersion,
          previousSessionId,
          reason: event.reason,
        }),
      heartbeatSample: () => heartbeatSampleFrom(ctx, activity),
      onNotice: (message, level) => ctx.ui.notify(message, level),
    });
    presence.start();
  });

  pi.on("session_shutdown", async () => {
    if (presence) {
      await presence.stop("shutdown");
      presence = undefined;
    }
  });

  pi.on("agent_start", async () => {
    activity.working = true;
  });

  pi.on("agent_settled", async () => {
    activity.working = false;
  });

  pi.registerCommand("remote", {
    description: "Show or change pi-remote registration: /remote [status|on|off]",
    handler: async (args, ctx) => {
      const action = parseRemoteAction(args);
      if (action === "invalid") {
        ctx.ui.notify("usage: /remote [status|on|off]", "warning");
        return;
      }
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
        if (presence.status().state === "disabled") {
          ctx.ui.notify("pi-remote: disabled by config (PI_REMOTE / pi-remote.json)", "warning");
          return;
        }
        presence.start();
        ctx.ui.notify("pi-remote: on", "info");
        return;
      }
      const status = presence.status();
      ctx.ui.notify(statusText(status), status.state === "online" ? "info" : "warning");
    },
  });
}
