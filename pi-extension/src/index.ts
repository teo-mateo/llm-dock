import type { ExtensionAPI, ExtensionEvent } from "@earendil-works/pi-coding-agent";

import { Type } from "typebox";

import { registerAskUser } from "./ask-user.ts";
import { createActivity } from "./activity.ts";
import { detectPiVersion, loadConfig, readExtVersion } from "./config.ts";
import { handleRemoteCommand } from "./remote-command-handler.ts";
import { parentSessionIdFrom } from "./pi-adapter.ts";
import { createSessionRuntime, type SessionRuntime } from "./session-runtime.ts";
import { sessionIdFromFile } from "./session.ts";
import { registerEventSubscriptions } from "./subscriptions.ts";

export default function (pi: ExtensionAPI) {
  const config = loadConfig();
  const extVersion = readExtVersion(import.meta.url);
  const piVersion = detectPiVersion();
  const parentSessionId = parentSessionIdFrom(process.env);
  const activity = createActivity();
  let runtime: SessionRuntime | undefined;

  const forward = (event: ExtensionEvent): void => {
    runtime?.handle(event);
  };
  registerEventSubscriptions(pi, forward);
  registerAskUser(pi, () => runtime, Type);

  pi.on("session_start", async (event, ctx) => {
    const previousSessionId = sessionIdFromFile(event.previousSessionFile);
    if (runtime) await runtime.stop("switch");
    runtime = createSessionRuntime({
      config,
      ctx,
      pi,
      event,
      extVersion,
      piVersion,
      previousSessionId,
      parentSessionId,
      activity,
    });
  });

  pi.on("session_shutdown", async () => {
    if (runtime) {
      await runtime.stop("shutdown");
      runtime = undefined;
    }
  });

  pi.registerCommand("remote", {
    description: "Show or change pi-remote registration: /remote [status|on|off]",
    handler: (args, ctx) => handleRemoteCommand(args, ctx, runtime),
  });
}
