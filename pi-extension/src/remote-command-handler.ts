import type { ExtensionCommandContext } from "@earendil-works/pi-coding-agent";

import type { Presence } from "./presence.ts";
import { parseRemoteAction, statusText } from "./remote-command.ts";

export async function handleRemoteCommand(
  args: string,
  ctx: ExtensionCommandContext,
  presence: Presence | undefined,
): Promise<void> {
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
}
