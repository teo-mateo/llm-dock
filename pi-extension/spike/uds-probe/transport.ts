import { request, type ClientRequest, type IncomingMessage } from "node:http";

export const DEFAULT_SOCKET_PATH =
  process.env.PI_REMOTE_SPIKE_SOCKET ??
  `${process.env.HOME ?? ""}/.cache/pi-remote/pi-remote-spike.sock`;

export function postJson(
  socketPath: string,
  path: string,
  payload: unknown,
): Promise<{ status: number; body: string }> {
  const body = JSON.stringify(payload);
  return new Promise((resolve, reject) => {
    const req = request(
      {
        socketPath,
        path,
        method: "POST",
        headers: {
          "content-type": "application/json",
          "content-length": Buffer.byteLength(body),
        },
      },
      (res) => {
        let data = "";
        res.setEncoding("utf8");
        res.on("data", (chunk) => {
          data += chunk;
        });
        res.on("end", () => resolve({ status: res.statusCode ?? 0, body: data }));
      },
    );
    req.on("error", reject);
    req.end(body);
  });
}

export function openStream(
  socketPath: string,
  path: string,
  onResponse: (res: IncomingMessage) => void,
): ClientRequest {
  const req = request(
    {
      socketPath,
      path,
      method: "GET",
      headers: { accept: "text/event-stream" },
    },
    onResponse,
  );
  req.end();
  return req;
}
