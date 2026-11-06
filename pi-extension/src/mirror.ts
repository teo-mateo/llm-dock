import type {
  AgentBeforeSettleEvent,
  ExtensionEvent,
  InputEvent,
  MessageEndEvent,
  MessageUpdateEvent,
  ModelSelectEvent,
  SessionCompactEvent,
  ThinkingLevelSelectEvent,
  ToolExecutionEndEvent,
  ToolExecutionStartEvent,
  ToolExecutionUpdateEvent,
  TurnEndEvent,
} from "@earendil-works/pi-coding-agent";

import type { Activity } from "./activity.ts";
import { DeltaCoalescer, type DeltaChunk } from "./coalesce.ts";
import {
  type EventBody,
  type EventOutcome,
  EventStamper,
  type WireEvent,
  assistantDeltaBody,
  assistantMessageBody,
  compactionBody,
  modelChangedBody,
  runEndBody,
  stateBody,
  thinkingChangedBody,
  toolEndBody,
  toolStartBody,
  toolUpdateBody,
  turnEndBody,
  userMessageBody,
} from "./events.ts";
import {
  contentText,
  contentThinking,
  isAssistant,
  messageModel,
  stopReasonOf,
  usageOf,
  modelRef,
} from "./message-content.ts";
import { ToolThrottle } from "./throttle.ts";
import { toolText } from "./tool-text.ts";

type MirrorOptions = {
  stamper: EventStamper;
  activity: Activity;
  emit: (event: WireEvent) => void;
};

export class EventMirror {
  private readonly stamper: EventStamper;
  private readonly activity: Activity;
  private readonly emitEvent: (event: WireEvent) => void;
  private readonly deltas = new DeltaCoalescer();
  private readonly tools = new ToolThrottle();
  private lastOutcome: EventOutcome = "completed";

  constructor(options: MirrorOptions) {
    this.stamper = options.stamper;
    this.activity = options.activity;
    this.emitEvent = options.emit;
  }

  handle(event: ExtensionEvent): void {
    switch (event.type) {
      case "input": this.onInput(event); break;
      case "agent_start": this.onAgentStart(); break;
      case "agent_before_settle": this.onBeforeSettle(event); break;
      case "agent_settled": this.onSettled(); break;
      case "message_update": this.onMessageUpdate(event); break;
      case "message_end": this.onMessageEnd(event); break;
      case "tool_execution_start": this.onToolStart(event); break;
      case "tool_execution_update": this.onToolUpdate(event); break;
      case "tool_execution_end": this.onToolEnd(event); break;
      case "turn_end": this.onTurnEnd(event); break;
      case "model_select": this.onModelSelect(event); break;
      case "thinking_level_select": this.onThinkingSelect(event); break;
      case "session_compact": this.onCompact(event); break;
    }
  }

  private emitBody(body: EventBody): void {
    this.emitEvent(this.stamper.stamp(body));
  }

  private onInput(event: InputEvent): void {
    this.emitBody(userMessageBody(
      event.text,
      event.images?.length ?? 0,
      event.source === "interactive" ? "terminal" : "extension",
    ));
  }

  private onAgentStart(): void {
    this.lastOutcome = "completed";
    this.activity.working = true;
    this.emitBody(stateBody("working"));
  }

  private onBeforeSettle(event: AgentBeforeSettleEvent): void { this.lastOutcome = event.outcome; }

  private onSettled(): void {
    this.activity.working = false;
    this.emitBody(runEndBody(this.lastOutcome));
    this.emitBody(stateBody("idle"));
  }

  private onMessageUpdate(event: MessageUpdateEvent): void {
    const now = this.stamper.now();
    const assistant = event.assistantMessageEvent;
    let chunks: DeltaChunk[] = [];
    if (assistant.type === "text_delta") {
      chunks = this.deltas.addText(assistant.delta, now);
    } else if (assistant.type === "thinking_delta") {
      chunks = this.deltas.addThinking(assistant.delta, now);
    }
    for (const chunk of chunks) {
      this.emitBody(assistantDeltaBody(chunk.text, chunk.thinking));
    }
  }

  private onMessageEnd(event: MessageEndEvent): void {
    if (!isAssistant(event.message)) return;
    const now = this.stamper.now();
    for (const chunk of this.deltas.flush(now)) {
      this.emitBody(assistantDeltaBody(chunk.text, chunk.thinking));
    }
    this.emitBody(assistantMessageBody(
      contentText(event.message),
      contentThinking(event.message),
      messageModel(event.message),
      usageOf(event.message),
      stopReasonOf(event.message),
    ));
  }

  private onToolStart(event: ToolExecutionStartEvent): void {
    const args = toolText(event.args);
    this.emitBody(toolStartBody(event.toolCallId, event.toolName, args.text, args.truncated));
  }

  private onToolUpdate(event: ToolExecutionUpdateEvent): void {
    const now = this.stamper.now();
    if (!this.tools.allow(event.toolCallId, now)) return;
    const partial = toolText(event.partialResult);
    this.emitBody(toolUpdateBody(
      event.toolCallId, event.toolName, partial.text, partial.truncated,
    ));
  }

  private onToolEnd(event: ToolExecutionEndEvent): void {
    this.tools.done(event.toolCallId);
    const result = toolText(event.result);
    this.emitBody(toolEndBody(
      event.toolCallId,
      event.toolName,
      result.text,
      event.isError,
      event.durationMs ?? null,
      result.truncated,
    ));
  }

  private onTurnEnd(event: TurnEndEvent): void {
    if (event.outcome !== "completed") this.lastOutcome = event.outcome;
    this.emitBody(turnEndBody(event.outcome));
  }

  private onModelSelect(event: ModelSelectEvent): void {
    this.emitBody(modelChangedBody(modelRef(event.model), modelRef(event.previousModel)));
  }

  private onThinkingSelect(event: ThinkingLevelSelectEvent): void {
    this.emitBody(thinkingChangedBody(event.level, event.previousLevel));
  }

  private onCompact(event: SessionCompactEvent): void {
    this.emitBody(compactionBody(
      event.compactionEntry.summary,
      event.compactionEntry.tokensBefore ?? null,
      event.reason,
    ));
  }
}
