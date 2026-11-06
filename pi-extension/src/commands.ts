import type { Command, CommandResult } from "./protocol.ts";

export type { Command, CommandResult };

export type CommandHandler = (args: unknown) => void | Promise<void>;
export type CommandHandlers = Readonly<Record<string, CommandHandler>>;

export const COMMAND_RESULT_CAPACITY = 200;

function result(command: Command, ok: boolean, error: string | null): CommandResult {
  return { command_id: command.command_id, ok, error };
}

export async function dispatch(
  command: Command,
  handlers: CommandHandlers,
): Promise<CommandResult> {
  const handler = handlers[command.kind];
  if (!handler) return result(command, false, "unsupported_command");
  try {
    await handler(command.args);
    return result(command, true, null);
  } catch {
    return result(command, false, "failed");
  }
}

export class CommandDedupe {
  private readonly capacity: number;
  private readonly results = new Map<string, CommandResult>();

  constructor(capacity = COMMAND_RESULT_CAPACITY) {
    this.capacity = Math.max(0, capacity);
  }

  seen(id: string): CommandResult | undefined {
    return this.results.get(id);
  }

  record(result: CommandResult): void {
    if (this.results.has(result.command_id)) {
      this.results.set(result.command_id, result);
      return;
    }
    this.results.set(result.command_id, result);
    if (this.results.size > this.capacity) {
      const oldest = this.results.keys().next().value;
      if (oldest !== undefined) this.results.delete(oldest);
    }
  }
}
