export type FakeClock = ReturnType<typeof fakeClock>;

export function fakeClock(start = 0) {
  let now = start;
  let seq = 0;
  const timers = new Map<number, { at: number; fn: () => void }>();
  return {
    now: () => now,
    setTimeout: (fn: () => void, ms: number) => {
      const id = ++seq;
      timers.set(id, { at: now + ms, fn });
      return id;
    },
    clearTimeout: (handle: unknown) => {
      timers.delete(handle as number);
    },
    advance: async (ms: number) => {
      now += ms;
      for (;;) {
        const due = [...timers.entries()]
          .filter(([, timer]) => timer.at <= now)
          .sort((a, b) => a[1].at - b[1].at);
        if (due.length === 0) return;
        for (const [id, timer] of due) {
          timers.delete(id);
          timer.fn();
          await Promise.resolve();
        }
      }
    },
    pending: () => [...timers.values()].map((timer) => timer.at - now).sort((a, b) => a - b),
  };
}

export async function flush(): Promise<void> {
  for (let i = 0; i < 10; i += 1) await Promise.resolve();
}
