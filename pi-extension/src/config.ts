import { readFileSync, realpathSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export const DEFAULT_SOCKET_PATH = "~/.cache/pi-remote/pi-remote.sock";
export const CONFIG_FILE = "~/.pi/agent/pi-remote.json";

export type RemoteConfig = {
  enabled: boolean;
  socketPath: string;
  configPath: string;
};

export type ConfigInput = {
  env?: Record<string, string | undefined>;
  home?: string;
  configText?: string | null;
};

function expandHome(path: string, home: string): string {
  if (path === "~") return home;
  if (path.startsWith("~/")) return join(home, path.slice(2));
  return path;
}

function readFileText(path: string): string | null {
  try {
    return readFileSync(path, "utf8");
  } catch {
    return null;
  }
}

export function resolveConfig(input: ConfigInput = {}): RemoteConfig {
  const env = input.env ?? process.env;
  const home = input.home ?? homedir();
  const configPath = join(home, ".pi/agent/pi-remote.json");

  let file: { enabled?: unknown; socket?: unknown } = {};
  const text = input.configText === undefined ? readFileText(configPath) : input.configText;
  if (text) {
    try {
      const parsed = JSON.parse(text);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        file = parsed as { enabled?: unknown; socket?: unknown };
      }
    } catch {
      file = {};
    }
  }

  const envRemote = env.PI_REMOTE;
  const enabled = envRemote !== undefined ? envRemote !== "0" : file.enabled !== false;
  const envSocket = env.PI_REMOTE_SOCKET;
  const rawSocket =
    (typeof envSocket === "string" && envSocket.length > 0 ? envSocket : undefined) ??
    (typeof file.socket === "string" && file.socket.length > 0 ? file.socket : DEFAULT_SOCKET_PATH);

  return {
    enabled,
    socketPath: expandHome(rawSocket, home),
    configPath,
  };
}

export function readExtVersion(moduleUrl: URL | string): string {
  try {
    const modulePath = realpathSync(fileURLToPath(moduleUrl));
    const parsed = JSON.parse(readFileSync(join(dirname(modulePath), "..", "package.json"), "utf8"));
    return typeof parsed.version === "string" ? parsed.version : "0.0.0";
  } catch {
    return "0.0.0";
  }
}

export function loadConfig(): RemoteConfig {
  return resolveConfig();
}

export function detectPiVersion(env: Record<string, string | undefined> = process.env): string | null {
  if (env.PI_VERSION) return env.PI_VERSION;
  const packageDir = env.PI_PACKAGE_DIR;
  if (!packageDir) return null;
  try {
    const parsed = JSON.parse(readFileSync(join(packageDir, "package.json"), "utf8"));
    return typeof parsed.version === "string" ? parsed.version : null;
  } catch {
    return null;
  }
}
