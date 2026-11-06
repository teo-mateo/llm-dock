import type { ExtensionContext, ExtensionEvent, SessionStartEvent } from "@earendil-works/pi-coding-agent";

import type { Activity } from "./activity.ts";
import type { RemoteConfig } from "./config.ts";
import { EventStamper } from "./events.ts";
import { EventMirror } from "./mirror.ts";
import { heartbeatSampleFrom, helloFieldsFrom } from "./pi-adapter.ts";
import { Presence } from "./presence.ts";
import { EventSender } from "./sender.ts";

export type SessionRuntime = {
  presence: Presence;
  sender: EventSender;
  mirror: EventMirror;
  handle: (event: ExtensionEvent) => void;
  pause: () => Promise<void>;
  resume: () => void;
  stop: (reason: string) => Promise<void>;
};

export type SessionRuntimeOptions = {
  config: RemoteConfig;
  ctx: ExtensionContext;
  event: SessionStartEvent;
  instanceId: string;
  extVersion: string;
  piVersion: string | null;
  previousSessionId: string | null;
  activity: Activity;
};

export function createSessionRuntime(options: SessionRuntimeOptions): SessionRuntime {
  const clock = {
    now: () => Date.now(),
    setTimeout: (fn: () => void, ms: number) => setTimeout(fn, ms),
    clearTimeout: (handle: unknown) => clearTimeout(handle as NodeJS.Timeout),
  };
  let sender: EventSender | undefined;
  const presence = new Presence({
    socketPath: options.config.socketPath,
    enabled: options.config.enabled,
    clock,
    helloFields: () => helloFieldsFrom(options.ctx, {
      instanceId: options.instanceId,
      extVersion: options.extVersion,
      piVersion: options.piVersion,
      previousSessionId: options.previousSessionId,
      reason: options.event.reason,
    }),
    heartbeatSample: () => heartbeatSampleFrom(options.ctx, options.activity),
    onNotice: (message, level) => options.ctx.ui.notify(message, level),
    onOnline: (ackedSeq) => sender?.onOnline(ackedSeq),
  });
  sender = new EventSender({
    socketPath: options.config.socketPath,
    presence,
    clock,
  });
  options.activity.working = false;
  const stamper = new EventStamper(clock);
  const mirror = new EventMirror({
    stamper,
    activity: options.activity,
    emit: (event) => sender?.enqueue(event),
  });
  presence.start();
  let paused = false;
  return {
    presence,
    sender,
    mirror,
    handle: (event) => {
      if (!paused) mirror.handle(event);
    },
    pause: async () => {
      paused = true;
      await sender.stop();
      await presence.stop("remote_off");
    },
    resume: () => {
      paused = false;
      sender.start();
      presence.start();
    },
    stop: async (reason) => {
      paused = true;
      await sender.stop();
      await presence.stop(reason);
    },
  };
}
