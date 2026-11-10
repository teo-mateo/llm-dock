import type { WireEvent } from "./events.ts";

export const PROTOCOL_VERSION = 1;
export const MAX_EVENTS_BATCH = 50;
export const MAX_EVENTS_BODY_BYTES = 1024 * 1024;
export const MAX_COMMAND_WAIT_MS = 25_000;
export const COMMAND_REDELIVERY_MS = 30_000;

export const PATHS = {
  hello: "/v1/hello",
  heartbeat: "/v1/heartbeat",
  bye: "/v1/bye",
  events: "/v1/events",
  commandsPoll: "/v1/commands/poll",
  commandResults: "/v1/command-results",
} as const;

export type WirePath = (typeof PATHS)[keyof typeof PATHS];

export type SessionReason = "startup" | "reload" | "new" | "resume" | "fork";

export type ModelRef = {
  provider: string;
  id: string;
};

export type ContextUsage = {
  tokens: number | null;
  window: number | null;
  percent: number | null;
};

export type HelloFields = {
  session_id: string;
  instance_id: string;
  session_file: string | null;
  cwd: string;
  name: string | null;
  pid: number;
  model: ModelRef | null;
  thinking_level: string | null;
  reason: SessionReason;
  previous_session_id: string | null;
  parent_session_id: string | null;
  pi_version: string | null;
  ext_version: string;
};

export type HeartbeatFields = {
  session_id: string;
  instance_id: string;
  state: "idle" | "working";
  context: ContextUsage | null;
  sent_at: number;
};

export type ByeFields = {
  session_id: string;
  instance_id: string;
  reason: string | null;
};

export type HelloFrame = HelloFields & { protocol: number; type: "hello" };
export type HeartbeatFrame = HeartbeatFields & { protocol: number; type: "heartbeat" };
export type ByeFrame = ByeFields & { protocol: number; type: "bye" };

export type Command = {
  command_id: string;
  kind: string;
  args: unknown;
  issued_at: number;
};

export type CommandResult = {
  command_id: string;
  ok: boolean;
  error: string | null;
};

export type CommandsPollFields = {
  session_id: string;
  instance_id: string;
  wait_ms: number;
};

export type CommandsPollFrame = CommandsPollFields & { protocol: number; type: "commands_poll" };

export type CommandResultsFields = {
  session_id: string;
  instance_id: string;
  results: CommandResult[];
};

export type CommandResultsFrame = CommandResultsFields & { protocol: number; type: "command_results" };

export type EventsFields = {
  session_id: string;
  instance_id: string;
  events: WireEvent[];
};

export type EventsFrame = EventsFields & { protocol: number; type: "events" };

export type ServerResponse = {
  ok: boolean;
  protocol: number;
  error?: string;
  session_id?: string;
  instance_id?: string;
  server_time?: number;
  acked_seq?: number;
  commands?: Command[];
};

export function buildHello(fields: HelloFields): HelloFrame {
  return { protocol: PROTOCOL_VERSION, type: "hello", ...fields };
}

export function buildHeartbeat(fields: HeartbeatFields): HeartbeatFrame {
  return { protocol: PROTOCOL_VERSION, type: "heartbeat", ...fields };
}

export function buildBye(fields: ByeFields): ByeFrame {
  return { protocol: PROTOCOL_VERSION, type: "bye", ...fields };
}

export function buildEvents(fields: EventsFields): EventsFrame {
  return { protocol: PROTOCOL_VERSION, type: "events", ...fields };
}

export function buildCommandsPoll(fields: CommandsPollFields): CommandsPollFrame {
  return { protocol: PROTOCOL_VERSION, type: "commands_poll", ...fields };
}

export function buildCommandResults(fields: CommandResultsFields): CommandResultsFrame {
  return { protocol: PROTOCOL_VERSION, type: "command_results", ...fields };
}

export function parseResponse(text: string): ServerResponse | null {
  try {
    const value = JSON.parse(text) as unknown;
    if (
      value !== null &&
      typeof value === "object" &&
      typeof (value as ServerResponse).ok === "boolean" &&
      typeof (value as ServerResponse).protocol === "number"
    ) {
      return value as ServerResponse;
    }
    return null;
  } catch {
    return null;
  }
}

export type ResponseKind = "ok" | "unknown_session" | "bad_frame" | "rejected" | "unparseable";

export function classifyResponse(status: number, body: string): ResponseKind {
  const response = parseResponse(body);
  if (!response) return "unparseable";
  if (status === 404 && response.error === "unknown_session") return "unknown_session";
  if (status === 400 && response.error === "bad_frame") return "bad_frame";
  if (status === 200 && response.ok) return "ok";
  return "rejected";
}
