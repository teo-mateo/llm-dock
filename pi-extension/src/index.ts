import { randomUUID } from "node:crypto";

import type { ExtensionAPI, ExtensionEvent } from "@earendil-works/pi-coding-agent";

import { createActivity } from "./activity.ts";
import { detectPiVersion, loadConfig, readExtVersion } from "./config.ts";
import { handleRemoteCommand } from "./remote-command-handler.ts";
import { createSessionRuntime, type SessionRuntime } from "./session-runtime.ts";
import { sessionIdFromFile } from "./session.ts";
import { registerEventSubscriptions } from "./subscriptions.ts";

export default function (pi: ExtensionAPI) {
  const config = loadConfig();
  const instanceId = randomUUID();
  const extVersion = readExtVersion(new URL("../package.json", import.meta.url));
  const piVersion = detectPiVersion();
  const activity = createActivity();
  let runtime: SessionRuntime | undefined;

  const forward = (event: ExtensionEvent): void => {
    runtime?.mirror.handle(event);
  };
  registerEventSubscriptions(pi, forward);

  pi.on("session_start", async (event, ctx) => {
    activity.working = false;
    const previousSessionId = sessionIdFromFile(event.previousSessionFile);
    if (runtime) await runtime.stop("switch");
    runtime = createSessionRuntime({
      config,
      ctx,
      event,
      instanceId,
      extVersion,
      piVersion,
      previousSessionId,
      activity,
    });
  });

  pi.on("session_shutdown", async () => {
    if (runtime) {
      await runtime.stop("shutdown");
      runtime = undefined;
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
    handler: (args, ctx) => handleRemoteCommand(args, ctx, runtime?.presence),
  });
}
