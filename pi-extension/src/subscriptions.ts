import type { ExtensionAPI, ExtensionEvent } from "@earendil-works/pi-coding-agent";

export function registerEventSubscriptions(
  pi: ExtensionAPI,
  forward: (event: ExtensionEvent) => void,
): void {
  pi.on("input", forward);
  pi.on("agent_start", forward);
  pi.on("agent_before_settle", forward);
  pi.on("agent_settled", forward);
  pi.on("message_start", forward);
  pi.on("message_update", forward);
  pi.on("message_end", forward);
  pi.on("tool_execution_start", forward);
  pi.on("tool_execution_update", forward);
  pi.on("tool_execution_end", forward);
  pi.on("turn_end", forward);
  pi.on("model_select", forward);
  pi.on("thinking_level_select", forward);
  pi.on("session_compact", forward);
}
