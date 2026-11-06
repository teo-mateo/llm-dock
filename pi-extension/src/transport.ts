import { request } from "node:http";

export type TransportResult = { status: number; body: string };

export type RequestFn = (
  socketPath: string,
  path: string,
  payload: unknown,
  timeoutMs: number,
) => Promise<TransportResult>;

export class TransportError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "TransportError";
    this.code = code;
  }
}

export const postJson: RequestFn = (socketPath, path, payload, timeoutMs) => {
  const data = JSON.stringify(payload);
  return new Promise((resolve, reject) => {
    const req = request(
      {
        socketPath,
        path,
        method: "POST",
        headers: {
          "content-type": "application/json",
          "content-length": Buffer.byteLength(data),
        },
      },
      (res) => {
        let body = "";
        res.setEncoding("utf8");
        res.on("data", (chunk: string) => {
          body += chunk;
        });
        res.on("end", () => resolve({ status: res.statusCode ?? 0, body }));
      },
    );
    req.setTimeout(timeoutMs, () => {
      req.destroy(new TransportError("timeout", `timeout after ${timeoutMs} ms`));
    });
    req.on("error", (err) => {
      if (err instanceof TransportError) {
        reject(err);
        return;
      }
      const code = (err as NodeJS.ErrnoException).code ?? "error";
      reject(new TransportError(code, err.message));
    });
    req.end(data);
  });
};
