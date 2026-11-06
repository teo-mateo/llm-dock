import type { ExtensionCommandContext } from "@earendil-works/pi-coding-agent";

import { parseRemoteAction, statusText } from "./remote-command.ts";
import type { SessionRuntime } from "./session-runtime.ts";

export async function handleRemoteCommand(
  args: string,
  ctx: ExtensionCommandContext,
  runtime: SessionRuntime | undefined,
): Promise<void> {
  const action = parseRemoteAction(args);
  if (action === "invalid") {
    ctx.ui.notify("usage: /remote [status|on|off]", "warning");
    return;
  }
  if (!runtime) {
    ctx.ui.notify("pi-remote: no session registration", "warning");
    return;
  }
  if (action === "off") {
    await runtime.pause();
    ctx.ui.notify("pi-remote: off", "info");
    return;
  }
  if (action === "on") {
    if (runtime.presence.status().state === "disabled") {
      ctx.ui.notify("pi-remote: disabled by config (PI_REMOTE / pi-remote.json)", "warning");
      return;
    }
    runtime.resume();
    ctx.ui.notify("pi-remote: on", "info");
    return;
  }
  const status = runtime.presence.status();
  ctx.ui.notify(statusText(status), status.state === "online" ? "info" : "warning");
}
