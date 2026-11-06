import type { ExtensionContext } from "@earendil-works/pi-coding-agent";

export type DialogKind = "select" | "confirm" | "input";

export type DialogOptions = { abortMs?: number; timeoutMs?: number };

export type DialogResult = {
  kind: DialogKind;
  mode: "abort" | "timeout" | "interactive";
  result: unknown;
  elapsedMs: number;
};

export async function runDialog(
  ctx: ExtensionContext,
  kind: DialogKind,
  options: DialogOptions,
): Promise<DialogResult> {
  const controller = new AbortController();
  const abortMs = options.abortMs;
  const timeoutMs = options.timeoutMs;
  const timer = abortMs === undefined ? undefined : setTimeout(() => controller.abort(), abortMs);
  const dialogOptions = {
    ...(abortMs === undefined ? {} : { signal: controller.signal }),
    ...(timeoutMs === undefined ? {} : { timeout: timeoutMs }),
  };
  const started = Date.now();
  try {
    let result: unknown;
    if (kind === "select") {
      result = await ctx.ui.select("probe select", ["alpha", "beta"], dialogOptions);
    } else if (kind === "confirm") {
      result = await ctx.ui.confirm("probe confirm", "pick yes or no", dialogOptions);
    } else {
      result = await ctx.ui.input("probe input", "type something", dialogOptions);
    }
    const mode = abortMs !== undefined ? "abort" : timeoutMs !== undefined ? "timeout" : "interactive";
    return { kind, mode, result, elapsedMs: Date.now() - started };
  } finally {
    if (timer) clearTimeout(timer);
  }
}
