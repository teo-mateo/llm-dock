import { randomUUID } from "node:crypto";
import type { ExtensionAPI, ExtensionContext, ExtensionEvent, SessionStartEvent } from "@earendil-works/pi-coding-agent";

import { CommandPoller } from "./command-poller.ts";
import { Delivery } from "./delivery.ts";
import { userMessageContent } from "./message-content.ts";
import { createAnswerPromptHandler, RemotePrompts } from "./remote-prompts.ts";
import { createSendMessageHandler, type SendPort } from "./send-message.ts";

import type { Activity } from "./activity.ts";
import type { RemoteConfig } from "./config.ts";
import { EventStamper } from "./events.ts";
import { EventMirror } from "./mirror.ts";
import { heartbeatSampleFrom, helloFieldsFrom, parentSessionIdFrom } from "./pi-adapter.ts";
import { Presence } from "./presence.ts";
import { EventSender } from "./sender.ts";

export type SessionRuntime = {
  presence: Presence;
  sender: EventSender;
  mirror: EventMirror;
  remotePrompts: RemotePrompts;
  handle: (event: ExtensionEvent) => void;
  pause: () => Promise<void>;
  resume: () => void;
  stop: (reason: string) => Promise<void>;
};

export type SessionRuntimeOptions = {
  config: RemoteConfig;
  ctx: ExtensionContext;
  pi: ExtensionAPI;
  event: SessionStartEvent;
  extVersion: string;
  piVersion: string | null;
  previousSessionId: string | null;
  activity: Activity;
};

export function createSessionRuntime(options: SessionRuntimeOptions): SessionRuntime {
  const instanceId = randomUUID();
  const clock = {
    now: () => Date.now(),
    setTimeout: (fn: () => void, ms: number) => setTimeout(fn, ms),
    clearTimeout: (handle: unknown) => clearTimeout(handle as NodeJS.Timeout),
  };
  let sender: EventSender | undefined;
  let poller: CommandPoller | undefined;
  const delivery = new Delivery();
  const sendPort: SendPort = {
    isIdle: () => options.ctx.isIdle(),
    send: (text, mode) => {
      if (mode === "steer") {
        options.pi.sendUserMessage(text, { deliverAs: "steer", expandPromptTemplates: false });
      } else {
        options.pi.sendUserMessage(text, { expandPromptTemplates: false });
      }
    },
    notify: (text) => options.ctx.ui.notify(text),
  };
  const presence = new Presence({
    socketPath: options.config.socketPath,
    enabled: options.config.enabled,
    clock,
    helloFields: () => helloFieldsFrom(options.ctx, {
      instanceId,
      extVersion: options.extVersion,
      piVersion: options.piVersion,
      previousSessionId: options.previousSessionId,
      parentSessionId: parentSessionIdFrom(process.env),
      reason: options.event.reason,
    }),
    heartbeatSample: () => heartbeatSampleFrom(options.ctx, options.activity),
    onNotice: (message, level) => options.ctx.ui.notify(message, level),
    onOnline: (ackedSeq) => {
      sender?.onOnline(ackedSeq);
      poller?.start();
      remotePrompts.replayOpen();
    },
  });
  sender = new EventSender({
    socketPath: options.config.socketPath,
    presence,
    clock,
  });
  const stamper = new EventStamper(clock);
  const remotePrompts = new RemotePrompts({
    stamper,
    emit: (event) => sender?.enqueue(event),
    clock,
  });
  poller = new CommandPoller({
    socketPath: options.config.socketPath,
    presence,
    clock,
    handlers: {
      abort: () => options.ctx.abort(),
      send_message: createSendMessageHandler(sendPort, delivery, clock.now),
      answer_prompt: createAnswerPromptHandler(remotePrompts),
    },
  });
  options.activity.working = false;
  const mirror = new EventMirror({
    stamper,
    activity: options.activity,
    emit: (event) => sender?.enqueue(event),
  });
  presence.start();
  poller.start();
  let paused = false;
  return {
    presence,
    sender,
    mirror,
    remotePrompts,
    handle: (event) => {
      if (paused) return;
      mirror.handle(event);
      if (event.type === "message_start") {
        const user = userMessageContent(event.message);
        if (user) delivery.observe(user.text, user.imageCount);
      } else if (event.type === "agent_settled") {
        for (const entry of delivery.settle()) sendPort.send(entry.text, "turn");
      }
    },
    pause: async () => {
      paused = true;
      poller?.pause();
      await sender.stop();
      await presence.stop("remote_off");
    },
    resume: () => {
      paused = false;
      poller?.start();
      sender.start();
      presence.start();
    },
    stop: async (reason) => {
      paused = true;
      poller?.stop();
      await sender.stop();
      await presence.stop(reason);
    },
  };
}
