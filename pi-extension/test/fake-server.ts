import { chmodSync, existsSync, unlinkSync } from "node:fs";
import { createServer, type ServerResponse } from "node:http";
import { pathToFileURL } from "node:url";

export type FakeRecord = {
  at: number;
  path: string;
  body: unknown;
  status: number;
};

export type FakeServer = {
  socketPath: string;
  records: FakeRecord[];
  sessions: Map<string, string>;
  close: () => Promise<void>;
  clearSessions: () => void;
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
  return parts.join(" ");
}

function handleFrame(
  path: string,
  frame: Record<string, unknown>,
  sessions: Map<string, string>,
): { status: number; payload: unknown } {
  if (frame.protocol !== 1) {
    return { status: 400, payload: { ok: false, protocol: 1, error: "unsupported_protocol" } };
  }
  const sessionId = typeof frame.session_id === "string" ? frame.session_id : "";
  const instanceId = typeof frame.instance_id === "string" ? frame.instance_id : "";
  if (!sessionId || !instanceId) {
    return { status: 400, payload: { ok: false, protocol: 1, error: "bad_frame" } };
  }
  if (path === "/v1/hello") {
    sessions.set(sessionId, instanceId);
    return {
      status: 200,
      payload: { ok: true, protocol: 1, session_id: sessionId, instance_id: instanceId, server_time: Date.now() },
    };
  }
  if (path === "/v1/heartbeat") {
    if (!sessions.has(sessionId)) {
      return { status: 404, payload: { ok: false, protocol: 1, error: "unknown_session" } };
    }
    return { status: 200, payload: { ok: true, protocol: 1, server_time: Date.now() } };
  }
  if (path === "/v1/bye") {
    if (!sessions.delete(sessionId)) {
      return { status: 404, payload: { ok: false, protocol: 1, error: "unknown_session" } };
    }
    return { status: 200, payload: { ok: true, protocol: 1 } };
  }
  return { status: 404, payload: { ok: false, protocol: 1, error: "not_found" } };
}

export function startFakeServer(socketPath: string): Promise<FakeServer> {
  if (existsSync(socketPath)) unlinkSync(socketPath);
  const sessions = new Map<string, string>();
  const records: FakeRecord[] = [];

  const server = createServer((req, res: ServerResponse) => {
    let raw = "";
    req.setEncoding("utf8");
    req.on("data", (chunk: string) => {
      raw += chunk;
    });
    req.on("end", () => {
      const path = req.url ?? "";
      const body = parseJson(raw);
      const record: FakeRecord = { at: Date.now(), path, body, status: 0 };
      records.push(record);

      let result: { status: number; payload: unknown };
      if (!body || typeof body !== "object" || Array.isArray(body)) {
        result = { status: 400, payload: { ok: false, protocol: 1, error: "bad_frame" } };
      } else {
        result = handleFrame(path, body as Record<string, unknown>, sessions);
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
        sessions,
        close: () =>
          new Promise<void>((done) => {
            server.close(() => done());
          }),
        clearSessions: () => {
          sessions.clear();
          console.log(`[${timestamp()}] sessions cleared (simulated dashboard restart)`);
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
  process.on("SIGUSR1", () => fake.clearSessions());
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
