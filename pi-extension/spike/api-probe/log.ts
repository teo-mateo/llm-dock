import { mkdirSync, appendFileSync } from "node:fs";
import { dirname } from "node:path";

const LOG_ROOT = "/tmp/pi-api-probe";

export function probeLogPath(sessionId: string): string {
  return `${LOG_ROOT}/${sessionId}.log`;
}

export function appendProbeLine(path: string, line: string): void {
  mkdirSync(dirname(path), { recursive: true });
  appendFileSync(path, `${new Date().toISOString()} ${line}\n`);
}
