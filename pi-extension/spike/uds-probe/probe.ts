import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

import { DEFAULT_SOCKET_PATH, openStream, postJson } from "./transport.ts";
import { parseSseChunk } from "./sse.ts";

const MAX_BACKOFF_MS = 15000;
const BASE_BACKOFF_MS = 1000;

export default function (pi: ExtensionAPI) {
  let stream: ReturnType<typeof openStream> | undefined;
  let retryTimer: NodeJS.Timeout | undefined;
  let attempt = 0;
  let stopped = false;

  function stopSession() {
    stopped = true;
    if (retryTimer) {
      clearTimeout(retryTimer);
      retryTimer = undefined;
    }
    if (stream) {
      stream.destroy();
      stream = undefined;
    }
  }

  function scheduleReconnect(ctx: ExtensionContext) {
    if (stopped) return;
    stream = undefined;
    if (retryTimer) return;
    attempt += 1;
    const delay = Math.min(BASE_BACKOFF_MS * 2 ** (attempt - 1), MAX_BACKOFF_MS);
    ctx.ui.notify(`events stream lost; retrying in ${delay} ms (attempt ${attempt})`, "warning");
    retryTimer = setTimeout(() => {
      retryTimer = undefined;
      connectEvents(ctx);
    }, delay);
  }

  function connectEvents(ctx: ExtensionContext) {
    if (stopped || stream) return;
    const req = openStream(DEFAULT_SOCKET_PATH, "/events", (res) => {
      if (stopped) {
        res.destroy();
        return;
      }
      if (res.statusCode !== 200) {
        ctx.ui.notify(`events -> unexpected status ${res.statusCode}`, "warning");
        scheduleReconnect(ctx);
        return;
      }
      attempt = 0;
      ctx.ui.notify("events stream connected", "info");
      let buffer = "";
      res.setEncoding("utf8");
      res.on("data", (chunk: string) => {
        const parsed = parseSseChunk(buffer, chunk);
        buffer = parsed.buffer;
        for (const data of parsed.events) {
          ctx.ui.notify(`event ${data}`, "info");
        }
      });
      res.on("end", () => scheduleReconnect(ctx));
      res.on("error", () => scheduleReconnect(ctx));
    });
    stream = req;
    req.on("error", (err) => {
      if (stopped) return;
      if (stream === req) stream = undefined;
      const code = (err as NodeJS.ErrnoException).code ?? "error";
      ctx.ui.notify(`events stream error [${code}]: ${err.message}`, "warning");
      scheduleReconnect(ctx);
    });
  }

  async function greet(ctx: ExtensionContext) {
    try {
      const res = await postJson(DEFAULT_SOCKET_PATH, "/hello", {
        session_id: ctx.sessionManager.getSessionId(),
        cwd: ctx.cwd,
        model: ctx.model?.id ?? null,
      });
      ctx.ui.notify(`hello -> ${res.status} ${res.body}`, "info");
    } catch (err) {
      const code = (err as NodeJS.ErrnoException).code ?? "error";
      ctx.ui.notify(`hello failed [${code}]: ${(err as Error).message}`, "warning");
    }
  }

  pi.on("session_start", async (_event, ctx) => {
    stopped = false;
    attempt = 0;
    await greet(ctx);
    connectEvents(ctx);
  });

  pi.on("session_shutdown", async () => {
    stopSession();
  });
}
