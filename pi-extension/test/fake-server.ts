import { chmodSync, existsSync, unlinkSync } from "node:fs";
import { createServer, type ServerResponse } from "node:http";
import { pathToFileURL } from "node:url";

import { MAX_EVENTS_BODY_BYTES, PATHS } from "../src/protocol.ts";
import { commandKey, FakeCommands, handleCommandResults, handleCommandsPoll, STALE_AFTER_MS } from "./fake-commands.ts";
import { ackedSeq, handleEvents, type EventStore } from "./fake-events.ts";

export type RegistryEntry = { sessionId: string; instanceId: string; lastSeen: number };
export type Registry = Map<string, RegistryEntry>;

export type Frame = Record<string, unknown>;

export type FakeRecord = {
  at: number;
  path: string;
  body: unknown;
  status: number;
};

export type FakeServer = {
  socketPath: string;
  records: FakeRecord[];
  registry: Registry;
  events: EventStore;
  commands: FakeCommands;
  close: () => Promise<void>;
  clearSessions: (dropEvents?: boolean) => void;
};

function timestamp(): string {
  return new Date().toISOString().slice(11, 23);
}

function parseJson(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function bodySummary(body: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const key of ["session_id", "instance_id", "state", "reason", "name", "cwd"]) {
    if (body[key] !== undefined) parts.push(`${key}=${String(body[key])}`);
  }
  const model = body.model as { provider?: string; id?: string } | undefined;
  if (model?.provider && model?.id) parts.push(`model=${model.provider}/${model.id}`);
  if (Array.isArray(body.events)) {
    parts.push(`events=${body.events.map((event) => {
      const typed = event as { type?: string; seq?: number; outcome?: string; origin?: string };
      return `${typed.type}:${typed.seq}${typed.origin ? `/${typed.origin}` : ""}${typed.outcome ? `/${typed.outcome}` : ""}`;
    }).join(",")}`);
  }
  if (Array.isArray(body.commands)) {
    parts.push(`commands=${body.commands.map((command) => {
      const typed = command as { command_id?: string; kind?: string };
      return `${typed.command_id}:${typed.kind}`;
    }).join(",")}`);
  }
  if (Array.isArray(body.results)) {
    parts.push(`results=${body.results.map((result) => {
      const typed = result as { command_id?: string; ok?: boolean; error?: string | null };
      return `${typed.command_id}:${typed.ok}:${typed.error ?? "-"}`;
    }).join(",")}`);
  }
  return parts.join(" ");
}

function expectedType(path: string): "hello" | "heartbeat" | "bye" | "events" | "commands_poll" | "command_results" | null {
  if (path === PATHS.hello) return "hello";
  if (path === PATHS.heartbeat) return "heartbeat";
  if (path === PATHS.bye) return "bye";
  if (path === PATHS.events) return "events";
  if (path === PATHS.commandsPoll) return "commands_poll";
  if (path === PATHS.commandResults) return "command_results";
  return null;
}

function keyOf(sessionId: string, instanceId: string): string {
  return `${sessionId}|${instanceId}`;
}

export function handleFrame(
  path: string,
  frame: Frame,
  registry: Registry,
  now = Date.now(),
  eventsByKey: EventStore = new Map(),
): { status: number; payload: unknown } {
  const type = expectedType(path);
  if (!type) {
    return { status: 404, payload: { ok: false, protocol: 1, error: "not_found" } };
  }
  if (frame.protocol !== 1) {
    return { status: 400, payload: { ok: false, protocol: 1, error: "unsupported_protocol" } };
  }
  if (frame.type !== type) {
    return { status: 400, payload: { ok: false, protocol: 1, error: "bad_frame" } };
  }
  const sessionId = typeof frame.session_id === "string" ? frame.session_id : "";
  const instanceId = typeof frame.instance_id === "string" ? frame.instance_id : "";
  if (!sessionId || !instanceId) {
    return { status: 400, payload: { ok: false, protocol: 1, error: "bad_frame" } };
  }

  const key = keyOf(sessionId, instanceId);
  const stored = eventsByKey.get(key) ?? new Map();
  if (path === PATHS.hello) {
    registry.set(key, { sessionId, instanceId, lastSeen: now });
    return {
      status: 200,
      payload: {
        ok: true,
        protocol: 1,
        session_id: sessionId,
        instance_id: instanceId,
        server_time: now,
        acked_seq: ackedSeq(stored),
      },
    };
  }

  const entry = registry.get(key);
  if (!entry || now - entry.lastSeen > STALE_AFTER_MS) {
    registry.delete(key);
    return { status: 404, payload: { ok: false, protocol: 1, error: "unknown_session" } };
  }

  if (path === PATHS.heartbeat) {
    entry.lastSeen = now;
    return { status: 200, payload: { ok: true, protocol: 1, server_time: now } };
  }

  if (path === PATHS.bye) {
    registry.delete(key);
    return { status: 200, payload: { ok: true, protocol: 1 } };
  }

  if (path === PATHS.commandsPoll || path === PATHS.commandResults) {
    return { status: 400, payload: { ok: false, protocol: 1, error: "bad_frame" } };
  }
  const result = handleEvents(frame, stored);
  if (result.status === 200) eventsByKey.set(key, stored);
  return result;
}

export function startFakeServer(socketPath: string): Promise<FakeServer> {
  if (existsSync(socketPath)) unlinkSync(socketPath);
  const registry: Registry = new Map();
  const events: EventStore = new Map();
  const commands = new FakeCommands();
  const records: FakeRecord[] = [];

  const server = createServer((req, res: ServerResponse) => {
    let raw = "";
    req.setEncoding("utf8");
    req.on("data", (chunk: string) => {
      raw += chunk;
    });
    req.on("end", async () => {
      const path = req.url ?? "";
      const body = parseJson(raw);
      const record: FakeRecord = { at: Date.now(), path, body, status: 0 };
      records.push(record);

      let result: { status: number; payload: unknown };
      if (req.method !== "POST") {
        result = { status: 404, payload: { ok: false, protocol: 1, error: "not_found" } };
      } else if (!expectedType(path)) {
        result = { status: 404, payload: { ok: false, protocol: 1, error: "not_found" } };
      } else if (path === PATHS.events && Buffer.byteLength(raw) > MAX_EVENTS_BODY_BYTES) {
        result = { status: 400, payload: { ok: false, protocol: 1, error: "bad_frame" } };
      } else if (!body || typeof body !== "object" || Array.isArray(body)) {
        result = { status: 400, payload: { ok: false, protocol: 1, error: "bad_frame" } };
      } else if (path === PATHS.commandsPoll) {
        result = await handleCommandsPoll(body as Frame, registry, commands);
      } else if (path === PATHS.commandResults) {
        result = handleCommandResults(body as Frame, registry, commands);
      } else {
        result = handleFrame(path, body as Frame, registry, Date.now(), events);
        if (path === PATHS.bye) {
          const frame = body as Record<string, unknown>;
          commands.wake(commandKey(String(frame.session_id), String(frame.instance_id)));
        }
      }

      record.status = result.status;
      res.writeHead(result.status, { "content-type": "application/json" });
      res.end(JSON.stringify(result.payload));
      const summary =
        typeof body === "object" && body !== null && !Array.isArray(body)
          ? bodySummary(body as Record<string, unknown>)
          : "body=<invalid>";
      console.log(`[${timestamp()}] POST ${path} ${result.status} ${summary}`);
    });
  });

  return new Promise((resolve, reject) => {
    server.on("error", reject);
    server.listen(socketPath, () => {
      chmodSync(socketPath, 0o600);
      console.log(`[${timestamp()}] listening on ${socketPath} (mode 0600)`);
      resolve({
        socketPath,
        records,
        registry,
        events,
        commands,
        close: () =>
          new Promise<void>((done) => {
            server.close(() => done());
          }),
        clearSessions: (dropEvents = false) => {
          registry.clear();
          if (dropEvents) events.clear();
          console.log(`[${timestamp()}] sessions cleared (simulated dashboard restart${dropEvents ? ", events dropped" : ""})`);
        },
      });
    });
  });
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  let socketPath = "/tmp/pi-remote-fake.sock";
  for (let i = 0; i < args.length; i += 1) {
    if (args[i] === "--socket" && args[i + 1]) {
      socketPath = args[i + 1];
      i += 1;
    }
  }
  const fake = await startFakeServer(socketPath);
  process.on("SIGUSR1", () => fake.clearSessions(true));
  process.on("SIGUSR2", () => {
    for (const key of fake.registry.keys()) {
      fake.commands.enqueue(key, fake.commands.abortCommand());
    }
    console.log(`[${timestamp()}] SIGUSR2 enqueued abort for ${fake.registry.size} session(s)`);
  });
  process.on("SIGHUP", () => {
    const text = "Reply with exactly REMOTE_OK and nothing else.";
    for (const key of fake.registry.keys()) {
      fake.commands.enqueue(key, fake.commands.sendCommand(text));
    }
    console.log(`[${timestamp()}] SIGHUP enqueued send_message for ${fake.registry.size} session(s)`);
  });
  const shutdown = async () => {
    await fake.close();
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  main().catch((err: Error) => {
    console.error(err.message);
    process.exit(1);
  });
}
