import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

import { runDialog, type DialogKind } from "./dialogs.ts";

export type ProbeCommandDeps = {
  pi: ExtensionAPI;
  log: (line: string) => void;
  logPath: () => string;
};

export function registerProbeCommands({ pi, log, logPath }: ProbeCommandDeps) {
  pi.registerCommand("probe-models", {
    description: "Log the model registry and scoped models",
    handler: async (_args, ctx) => {
      const available = ctx.modelRegistry.getAvailable();
      const all = ctx.modelRegistry.getAll();
      log(
        `models available=${available.length} all=${all.length} current=` +
          `${ctx.model?.provider ?? "?"}/${ctx.model?.id ?? "?"} scoped=${ctx.scopedModels.length} ` +
          `error=${ctx.modelRegistry.getError() ?? "none"}`,
      );
      for (const model of available) {
        log(
          `model available ${model.provider}/${model.id} name=${JSON.stringify(model.name)} api=${model.api} ` +
            `contextWindow=${model.contextWindow} maxTokens=${model.maxTokens} ` +
            `reasoning=${model.reasoning} input=${model.input.join("+")} ` +
            `hasAuth=${ctx.modelRegistry.hasConfiguredAuth(model)}`,
        );
      }
      for (const model of all) {
        if (available.some((candidate) => candidate.provider === model.provider && candidate.id === model.id)) continue;
        log(
          `model unavailable ${model.provider}/${model.id} name=${JSON.stringify(model.name)} ` +
            `hasAuth=${ctx.modelRegistry.hasConfiguredAuth(model)}`,
        );
      }
      for (const scoped of ctx.scopedModels) {
        log(`scoped model=${JSON.stringify(scoped).slice(0, 240)}`);
      }
      const found = ctx.modelRegistry.find("mistral", "mistral-small-latest");
      log(`find mistral/mistral-small-latest -> ${found ? `${found.provider}/${found.id}` : "none"}`);
      ctx.ui.notify(`logged ${available.length} available models to ${logPath()}`, "info");
    },
  });

  pi.registerCommand("probe-set-model", {
    description: "Switch model via pi.setModel: /probe-set-model provider/model-id",
    handler: async (args, ctx) => {
      const ref = args.trim();
      const slash = ref.indexOf("/");
      const provider = slash === -1 ? ref : ref.slice(0, slash);
      const modelId = slash === -1 ? "" : ref.slice(slash + 1);
      const model = ctx.modelRegistry.find(provider, modelId);
      log(
        `set_model request=${ref} found=${model ? `${model.provider}/${model.id}` : "none"} ` +
          `before=${ctx.model?.provider ?? "?"}/${ctx.model?.id ?? "?"}`,
      );
      if (!model) {
        ctx.ui.notify(`model not found: ${ref}`, "warning");
        return;
      }
      const ok = await pi.setModel(model);
      log(`set_model result=${ok} requested=${ref}`);
      ctx.ui.notify(`setModel ${ok ? "ok" : "failed"} -> ${ref}`, ok ? "info" : "warning");
    },
  });

  pi.registerCommand("probe-dialog", {
    description: "Open select|confirm|input, abort after N ms or time out: /probe-dialog kind [abortMs|none] [timeoutMs]",
    handler: async (args, ctx) => {
      const [kindArg, abortArg, timeoutArg] = args.trim().split(/\s+/);
      const kind: DialogKind = kindArg === "confirm" || kindArg === "input" ? kindArg : "select";
      const abortMs = !abortArg || abortArg === "none" ? undefined : Number(abortArg);
      const timeoutMs = timeoutArg ? Number(timeoutArg) : undefined;
      log(`dialog_start kind=${kind} abortMs=${abortMs ?? "none"} timeoutMs=${timeoutMs ?? "none"}`);
      const result = await runDialog(ctx, kind, { abortMs, timeoutMs });
      log(
        `dialog_end kind=${result.kind} mode=${result.mode} ` +
          `result=${JSON.stringify(result.result)} elapsedMs=${result.elapsedMs}`,
      );
      ctx.ui.notify(`dialog ${kind} -> ${result.mode} ${JSON.stringify(result.result)} (${result.elapsedMs} ms)`, "info");
    },
  });

  pi.registerCommand("probe-log", {
    description: "Show the probe log path",
    handler: async (_args, ctx) => {
      ctx.ui.notify(`probe log: ${logPath()}`, "info");
    },
  });
}
