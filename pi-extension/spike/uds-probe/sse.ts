export type ParsedSse = { buffer: string; events: string[] };

export function parseSseChunk(buffer: string, chunk: string): ParsedSse {
  let pending = buffer + chunk;
  const events: string[] = [];
  let boundary = pending.indexOf("\n\n");
  while (boundary !== -1) {
    const frame = pending.slice(0, boundary);
    pending = pending.slice(boundary + 2);
    const data = frame
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trim())
      .join("\n");
    if (data) events.push(data);
    boundary = pending.indexOf("\n\n");
  }
  return { buffer: pending, events };
}
