import { Delivery } from "./delivery.ts";
import type { CommandResult } from "./protocol.ts";

export const MAX_SEND_TEXT = 32000;

export type SendPort = {
  isIdle(): boolean;
  send(text: string, mode: "turn" | "steer"): void;
  notify(text: string): void;
};

export type SendMessageHandler = (
  args: { text: string },
  commandId?: string,
) => Promise<CommandResult>;

export function createSendMessageHandler(
  port: SendPort,
  delivery: Delivery,
  now: () => number,
): SendMessageHandler {
  let sequence = 0;
  return async (args, commandId) => {
    const text = typeof args?.text === "string" ? args.text : "";
    if (text.trim().length === 0 || text.length > MAX_SEND_TEXT) {
      return { command_id: "send-invalid", ok: false, error: "invalid_args" };
    }
    sequence += 1;
    const actualId = commandId ?? `send-${sequence}`;
    port.notify("📱 " + text.slice(0, 80));
    if (port.isIdle()) {
      port.send(text, "turn");
    } else {
      port.send(text, "steer");
      delivery.track(actualId, text, 0, now());
    }
    return { command_id: actualId, ok: true, error: null };
  };
}
