import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

import { DEFAULT_SOCKET_PATH, readExtVersion, resolveConfig } from "../src/config.ts";

const home = "/home/tester";
const fileSocket = "/run/file.sock";
const envSocket = "/run/env.sock";

test("default socket when no env or file", () => {
  const config = resolveConfig({ env: {}, home, configText: null });
  assert.equal(config.socketPath, `${home}/.cache/pi-remote/pi-remote.sock`);
  assert.equal(DEFAULT_SOCKET_PATH, "~/.cache/pi-remote/pi-remote.sock");
  assert.equal(config.enabled, true);
});

test("file socket beats the default", () => {
  const config = resolveConfig({
    env: {},
    home,
    configText: JSON.stringify({ socket: fileSocket }),
  });
  assert.equal(config.socketPath, fileSocket);
});

test("env socket beats the file", () => {
  const config = resolveConfig({
    env: { PI_REMOTE_SOCKET: envSocket },
    home,
    configText: JSON.stringify({ socket: fileSocket }),
  });
  assert.equal(config.socketPath, envSocket);
});

test("tilde is expanded against home", () => {
  const config = resolveConfig({
    env: { PI_REMOTE_SOCKET: "~/custom.sock" },
    home,
  });
  assert.equal(config.socketPath, `${home}/custom.sock`);
});

test("PI_REMOTE=0 disables and beats the file", () => {
  const config = resolveConfig({
    env: { PI_REMOTE: "0" },
    home,
    configText: JSON.stringify({ enabled: true }),
  });
  assert.equal(config.enabled, false);
});

test("PI_REMOTE=1 re-enables over a file disable", () => {
  const config = resolveConfig({
    env: { PI_REMOTE: "1" },
    home,
    configText: JSON.stringify({ enabled: false }),
  });
  assert.equal(config.enabled, true);
});

test("file enabled false disables when env is absent", () => {
  const config = resolveConfig({
    env: {},
    home,
    configText: JSON.stringify({ enabled: false }),
  });
  assert.equal(config.enabled, false);
});

test("malformed file is ignored", () => {
  const config = resolveConfig({ env: {}, home, configText: "not json" });
  assert.equal(config.enabled, true);
  assert.equal(config.socketPath, `${home}/.cache/pi-remote/pi-remote.sock`);
  assert.equal(config.configPath, `${home}/.pi/agent/pi-remote.json`);
});

function scratch(): string {
  return mkdtempSync(join(tmpdir(), "pi-ext-version-"));
}

test("reads the version when the extension is loaded through a symlink", () => {
  const root = scratch();
  try {
    const real = join(root, "real");
    mkdirSync(join(real, "src"), { recursive: true });
    writeFileSync(join(real, "package.json"), JSON.stringify({ version: "9.9.9" }));
    writeFileSync(join(real, "src", "index.ts"), "");
    symlinkSync(join(real, "src"), join(root, "link"), "dir");
    assert.equal(readExtVersion(pathToFileURL(join(root, "link", "index.ts"))), "9.9.9");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("falls back to 0.0.0 when the package file is missing", () => {
  const root = scratch();
  try {
    writeFileSync(join(root, "index.ts"), "");
    assert.equal(readExtVersion(pathToFileURL(join(root, "index.ts"))), "0.0.0");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
