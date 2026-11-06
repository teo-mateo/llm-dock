import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

import { registerProbeCommands } from "./probe-commands.ts";
import { appendProbeLine, probeLogPath } from "./log.ts";
import { scenarioByName, scenarioNames, type Scenario } from "./scenarios.ts";
import { findToken, hasToolCalls, summarizeEntry } from "./transcript.ts";

type Pending = { token: string; scenario: string; deliverAs: string; injectedAt: number };

export default function (pi: ExtensionAPI) {
  let logPath = probeLogPath("no-session");
  let seq = 0;
  let activeScenario: Scenario | undefined;
  let activeToken: string | undefined;
  let injected = false;
  let runCount = 0;
  const outstanding = new Map<string, Pending>();
  let latestCtx: ExtensionContext | undefined;

  function log(line: string) {
    appendProbeLine(logPath, line);
  }

  function injectNow(ctx: ExtensionContext) {
    if (!activeScenario || !activeToken || injected) return;
    injected = true;
    const injectedAt = Date.now();
    outstanding.set(activeToken, {
      token: activeToken,
      scenario: activeScenario.name,
      deliverAs: activeScenario.deliverAs,
      injectedAt,
    });
    log(
      `inject scenario=${activeScenario.name} token=${activeToken} deliverAs=${activeScenario.deliverAs} ` +
        `run=${runCount} idle=${ctx.isIdle()} pendingBefore=${ctx.hasPendingMessages()}`,
    );
    pi.sendUserMessage(`${activeScenario.injectedText} [${activeToken}]`, {
      deliverAs: activeScenario.deliverAs,
    });
  }

  function maybeInject(event: string, ctx: ExtensionContext, finalTurn = false) {
    if (!activeScenario || injected) return;
    const trigger = activeScenario.trigger;
    if (trigger.kind !== "event" || trigger.event !== event) return;
    if (trigger.finalTurnOnly && !finalTurn) return;
    injectNow(ctx);
  }

  function resetScenario() {
    activeScenario = undefined;
    activeToken = undefined;
    injected = false;
  }

  pi.on("session_start", async (_event, ctx) => {
    latestCtx = ctx;
    logPath = probeLogPath(ctx.sessionManager.getSessionId());
    log(
      `session_start session=${ctx.sessionManager.getSessionId()} cwd=${ctx.cwd} ` +
        `model=${ctx.model?.provider ?? "?"}/${ctx.model?.id ?? "?"} mode=${ctx.mode}`,
    );
  });

  pi.on("session_shutdown", async () => {
    log("session_shutdown");
  });

  pi.on("message_start", async (event, ctx) => {
    latestCtx = ctx;
    const role = (event.message as { role?: string })?.role ?? "?";
    log(`message_start role=${role} ${summarizeEntry(event.message)}`);
    for (const [token, pending] of outstanding) {
      if (findToken([event.message], token)) {
        log(
          `delivered token=${token} scenario=${pending.scenario} deliverAs=${pending.deliverAs} ` +
            `afterMs=${Date.now() - pending.injectedAt} run=${runCount} role=${role}`,
        );
        outstanding.delete(token);
      }
    }
  });

  pi.on("message_end", async (event, ctx) => {
    latestCtx = ctx;
    const role = (event.message as { role?: string })?.role ?? "?";
    log(`message_end role=${role}`);
  });

  pi.on("turn_start", async (event, ctx) => {
    latestCtx = ctx;
    log(`turn_start index=${event.turnIndex} idle=${ctx.isIdle()} pending=${ctx.hasPendingMessages()}`);
  });

  pi.on("turn_end", async (event, ctx) => {
    latestCtx = ctx;
    const toolCalls = hasToolCalls(event.message);
    log(
      `turn_end index=${event.turnIndex} toolCalls=${toolCalls} idle=${ctx.isIdle()} ` +
        `pending=${ctx.hasPendingMessages()} ${summarizeEntry(event.message)}`,
    );
    maybeInject("turn_end", ctx, !toolCalls);
  });

  pi.on("agent_start", async (_event, ctx) => {
    latestCtx = ctx;
    runCount += 1;
    log(`agent_start run=${runCount} idle=${ctx.isIdle()} pending=${ctx.hasPendingMessages()}`);
  });

  pi.on("agent_end", async (_event, ctx) => {
    latestCtx = ctx;
    log(`agent_end idle=${ctx.isIdle()} pending=${ctx.hasPendingMessages()}`);
    maybeInject("agent_end", ctx);
  });

  pi.on("agent_before_settle", async (event, ctx) => {
    latestCtx = ctx;
    log(
      `agent_before_settle outcome=${event.outcome} idle=${ctx.isIdle()} ` +
        `pending=${ctx.hasPendingMessages()}`,
    );
    maybeInject("agent_before_settle", ctx);
  });

  pi.on("agent_settled", async (_event, ctx) => {
    latestCtx = ctx;
    const delivered = activeToken ? findToken(ctx.sessionManager.getBranch(), activeToken) : false;
    log(
      `agent_settled run=${runCount} idle=${ctx.isIdle()} pending=${ctx.hasPendingMessages()} ` +
        `token=${activeToken ?? "none"} delivered=${delivered} ` +
        `outstanding=${[...outstanding.keys()].join(",") || "none"}`,
    );
    if (activeToken && !delivered) {
      log(
        `not_consumed token=${activeToken} scenario=${activeScenario?.name} ` +
          `run=${runCount} pending=${ctx.hasPendingMessages()}`,
      );
    }
    resetScenario();
  });

  pi.on("tool_execution_start", async (event, ctx) => {
    latestCtx = ctx;
    log(`tool_execution_start tool=${event.toolName} idle=${ctx.isIdle()} pending=${ctx.hasPendingMessages()}`);
  });

  pi.on("tool_execution_end", async (event, ctx) => {
    latestCtx = ctx;
    log(`tool_execution_end tool=${event.toolName}`);
  });

  pi.registerCommand("probe-scenario", {
    description: `Run an A2 delivery scenario (${scenarioNames()})`,
    handler: async (args, ctx) => {
      latestCtx = ctx;
      const name = args.trim();
      const scenario = scenarioByName(name);
      if (!scenario) {
        log(`scenario_unknown name=${name}`);
        ctx.ui.notify(`unknown scenario. known: ${scenarioNames()}`, "warning");
        return;
      }
      if (activeScenario) {
        log(`scenario_busy active=${activeScenario.name}`);
        ctx.ui.notify(`a scenario is already running (${activeScenario.name})`, "warning");
        return;
      }
      seq += 1;
      activeScenario = scenario;
      activeToken = `probe-${seq}-${Date.now().toString(36)}`;
      injected = false;
      log(
        `scenario_start name=${name} row=${scenario.row} token=${activeToken} ` +
          `deliverAs=${scenario.deliverAs} trigger=${JSON.stringify(scenario.trigger)} ` +
          `startPrompt=${scenario.startPrompt ?? "none"}`,
      );
      if (scenario.startPrompt) pi.sendUserMessage(scenario.startPrompt);
      if (scenario.trigger.kind === "delay") {
        const startedAt = Date.now();
        setTimeout(() => {
          if (!activeScenario || injected) {
            log(
              `inject_skipped scenario=${scenario.name} reason=settled_before_timer ` +
                `elapsedMs=${Date.now() - startedAt} run=${runCount}`,
            );
            return;
          }
          if (latestCtx) injectNow(latestCtx);
        }, scenario.trigger.ms);
      }
    },
  });

  pi.registerCommand("probe-inject", {
    description: "Send a user message now: /probe-inject steer|followUp [text]",
    handler: async (args, ctx) => {
      latestCtx = ctx;
      const [mode, ...rest] = args.trim().split(/\s+/);
      const deliverAs = mode === "followUp" ? "followUp" : "steer";
      seq += 1;
      const token = `probe-manual-${seq}-${Date.now().toString(36)}`;
      const text = `${rest.join(" ") || "reply with the single word OK"} [${token}]`;
      outstanding.set(token, { token, scenario: "manual", deliverAs, injectedAt: Date.now() });
      log(
        `inject scenario=manual token=${token} deliverAs=${deliverAs} ` +
          `idle=${ctx.isIdle()} pendingBefore=${ctx.hasPendingMessages()}`,
      );
      pi.sendUserMessage(text, { deliverAs });
    },
  });

  registerProbeCommands({ pi, log, logPath: () => logPath });

  pi.registerCommand("probe-close", {
    description: "Clear the active scenario without injecting",
    handler: async (_args, ctx) => {
      log(`scenario_closed active=${activeScenario?.name ?? "none"} injected=${injected}`);
      ctx.ui.notify("probe scenario cleared", "info");
      resetScenario();
    },
  });
}
