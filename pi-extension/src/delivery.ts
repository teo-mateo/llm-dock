export type Tracked = {
  commandId: string;
  contentHash: string;
  sentAt: number;
  resent: boolean;
  text: string;
};

export function contentHash(text: string, imageCount: number): string {
  const normalized = text.trim().replace(/\r\n/g, "\n");
  return JSON.stringify([normalized, imageCount]);
}

export class Delivery {
  private readonly entries: Tracked[] = [];

  track(commandId: string, text: string, imageCount: number, now: number): void {
    this.entries.push({
      commandId,
      contentHash: contentHash(text, imageCount),
      sentAt: now,
      resent: false,
      text,
    });
  }

  observe(userText: string, imageCount: number): string | null {
    const head = this.entries[0];
    if (!head || head.contentHash !== contentHash(userText, imageCount)) return null;
    this.entries.shift();
    return head.commandId;
  }

  settle(): Tracked[] {
    const unconfirmed = this.entries.filter((entry) => !entry.resent);
    for (const entry of unconfirmed) entry.resent = true;
    return unconfirmed;
  }

  pending(): number {
    return this.entries.length;
  }
}
