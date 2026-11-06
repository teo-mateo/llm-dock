export type DeliverAs = "steer" | "followUp";

export type TriggerEvent = "turn_end" | "agent_before_settle" | "agent_end" | "agent_settled";

export type Trigger =
  | { kind: "delay"; ms: number }
  | { kind: "event"; event: TriggerEvent; finalTurnOnly?: boolean };

export type Scenario = {
  name: string;
  row: string;
  startPrompt?: string;
  injectedText: string;
  deliverAs: DeliverAs;
  trigger: Trigger;
};

const COUNT_PROMPT =
  "Write the numbers from 1 to 60 in English words, one per line, in order. No code blocks, no explanation.";
const TOOL_PROMPT =
  "Use the bash tool to run exactly this command: sleep 6; echo done . Then report the command output.";
const INJECTED = "When you have finished, reply with the single word BRAVO and nothing else.";

function pair(row: string, startPrompt: string | undefined, trigger: Trigger): Scenario[] {
  return (["steer", "followUp"] as DeliverAs[]).map((deliverAs) => ({
    name: `${row}-${deliverAs === "followUp" ? "followup" : deliverAs}`,
    row,
    startPrompt,
    injectedText: INJECTED,
    deliverAs,
    trigger,
  }));
}

export const SCENARIOS: readonly Scenario[] = [
  ...pair("idle", undefined, { kind: "delay", ms: 200 }),
  ...pair("stream", COUNT_PROMPT, { kind: "delay", ms: 1500 }),
  ...pair("tool", TOOL_PROMPT, { kind: "delay", ms: 2500 }),
  ...pair("turnend", COUNT_PROMPT, { kind: "event", event: "turn_end", finalTurnOnly: true }),
  ...pair("settle", COUNT_PROMPT, { kind: "event", event: "agent_before_settle" }),
  ...pair("agentend", COUNT_PROMPT, { kind: "event", event: "agent_end" }),
];

export function scenarioByName(name: string): Scenario | undefined {
  return SCENARIOS.find((scenario) => scenario.name === name);
}

export function scenarioNames(): string {
  return SCENARIOS.map((scenario) => scenario.name).join(", ");
}
