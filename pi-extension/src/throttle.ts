export const TOOL_UPDATE_INTERVAL_MS = 250;

export class ToolThrottle {
  private readonly lastEmitted = new Map<string, number>();

  allow(callId: string, now: number): boolean {
    const last = this.lastEmitted.get(callId);
    if (last !== undefined && now - last < TOOL_UPDATE_INTERVAL_MS) return false;
    this.lastEmitted.set(callId, now);
    return true;
  }

  done(callId: string): void {
    this.lastEmitted.delete(callId);
  }
}
