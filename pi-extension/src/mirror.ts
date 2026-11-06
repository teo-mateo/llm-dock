import type {
  AgentBeforeSettleEvent,
  AgentSettledEvent,
  AgentStartEvent,
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

import { DeltaCoalescer, ToolThrottle, toolText } from "./coalesce.ts";
import {
  type EventOutcome,
  EventSequencer,
  type WireEvent,
  assistantDeltaEvent,
  assistantMessageEvent,
  compactionEvent,
  modelChangedEvent,
  runEndEvent,
  stateEvent,
  thinkingChangedEvent,
  toolEndEvent,
  toolStartEvent,
  toolUpdateEvent,
  turnEndEvent,
  userMessageEvent,
} from "./events.ts";
import { contentText, contentThinking, modelRef, usageOf } from "./message-content.ts";
import type { Clock } from "./presence-types.ts";

type MirrorOptions = {
  sequencer: EventSequencer;
  clock: Clock;
  emit: (event: WireEvent) => void;
};

export class EventMirror {
  private readonly sequencer: EventSequencer;
  private readonly clock: Clock;
  private readonly emitEvent: (event: WireEvent) => void;
  private readonly deltas = new DeltaCoalescer();
  private readonly tools = new ToolThrottle();
  private lastOutcome: EventOutcome = "completed";

  constructor(options: MirrorOptions) {
    this.sequencer = options.sequencer;
    this.clock = options.clock;
    this.emitEvent = options.emit;
  }

  handle(event: ExtensionEvent): void {
    switch (event.type) {
      case "input": this.onInput(event); break;
      case "agent_start": this.onAgentStart(event); break;
      case "agent_before_settle": this.onBeforeSettle(event); break;
      case "agent_settled": this.onSettled(event); break;
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

  private next(): number { return this.sequencer.next(); }
  private emit(event: WireEvent): void { this.emitEvent(event); }

  private onInput(event: InputEvent): void {
    this.emit(userMessageEvent(
      this.next(),
      this.clock.now(),
      event.text,
      event.images?.length ?? 0,
      event.source === "interactive" ? "terminal" : "extension",
    ));
  }

  private onAgentStart(_event: AgentStartEvent): void {
    this.lastOutcome = "completed";
    this.emit(stateEvent(this.next(), this.clock.now(), "working"));
  }

  private onBeforeSettle(event: AgentBeforeSettleEvent): void { this.lastOutcome = event.outcome; }

  private onSettled(_event: AgentSettledEvent): void {
    const now = this.clock.now();
    this.emit(runEndEvent(this.next(), now, this.lastOutcome));
    this.emit(stateEvent(this.next(), now, "idle"));
  }

  private onMessageUpdate(event: MessageUpdateEvent): void {
    const now = this.clock.now();
    const assistant = event.assistantMessageEvent;
    let chunks = [];
    if (assistant.type === "text_delta") {
      chunks = this.deltas.addText(assistant.delta, now);
    } else if (assistant.type === "thinking_delta") {
      chunks = this.deltas.addThinking(assistant.delta, now);
    }
    for (const chunk of chunks) {
      this.emit(assistantDeltaEvent(this.next(), now, chunk.text, chunk.thinking));
    }
  }

  private onMessageEnd(event: MessageEndEvent): void {
    const message = event.message as { role?: string };
    if (message.role !== "assistant") return;
    const now = this.clock.now();
    for (const chunk of this.deltas.flush(now)) {
      this.emit(assistantDeltaEvent(this.next(), now, chunk.text, chunk.thinking));
    }
    const typed = event.message as {
      provider?: string;
      model?: string;
      stopReason?: string;
      usage?: unknown;
    };
    const model = typeof typed.provider === "string" && typeof typed.model === "string"
      ? { provider: typed.provider, id: typed.model }
      : null;
    this.emit(assistantMessageEvent(
      this.next(),
      now,
      contentText(event.message),
      contentThinking(event.message),
      model,
      usageOf(event.message),
      typed.stopReason ?? null,
    ));
  }

  private onToolStart(event: ToolExecutionStartEvent): void {
    const args = toolText(event.args);
    this.emit(toolStartEvent(
      this.next(), this.clock.now(), event.toolCallId, event.toolName, args.text, args.truncated,
    ));
  }

  private onToolUpdate(event: ToolExecutionUpdateEvent): void {
    const now = this.clock.now();
    if (!this.tools.allow(event.toolCallId, now)) return;
    const partial = toolText(event.partialResult);
    this.emit(toolUpdateEvent(
      this.next(), now, event.toolCallId, event.toolName, partial.text, partial.truncated,
    ));
  }

  private onToolEnd(event: ToolExecutionEndEvent): void {
    this.tools.done(event.toolCallId);
    const result = toolText(event.result);
    this.emit(toolEndEvent(
      this.next(),
      this.clock.now(),
      event.toolCallId,
      event.toolName,
      result.text,
      event.isError,
      event.durationMs ?? null,
      result.truncated,
    ));
  }

  private onTurnEnd(event: TurnEndEvent): void { this.emit(turnEndEvent(this.next(), this.clock.now(), event.outcome)); }

  private onModelSelect(event: ModelSelectEvent): void {
    this.emit(modelChangedEvent(
      this.next(), this.clock.now(), modelRef(event.model), modelRef(event.previousModel),
    ));
  }

  private onThinkingSelect(event: ThinkingLevelSelectEvent): void {
    this.emit(thinkingChangedEvent(
      this.next(), this.clock.now(), event.level, event.previousLevel,
    ));
  }

  private onCompact(event: SessionCompactEvent): void {
    this.emit(compactionEvent(
      this.next(),
      this.clock.now(),
      event.compactionEntry.summary,
      event.compactionEntry.tokensBefore ?? null,
      event.reason,
    ));
  }
}
