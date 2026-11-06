export function sessionIdFromFile(file: string | null | undefined): string | null {
  if (!file) return null;
  const base = file.split("/").filter(Boolean).pop() ?? "";
  const stem = base.endsWith(".jsonl") ? base.slice(0, -".jsonl".length) : base;
  const underscore = stem.lastIndexOf("_");
  const candidate = underscore === -1 ? stem : stem.slice(underscore + 1);
  return candidate.length > 0 ? candidate : null;
}
