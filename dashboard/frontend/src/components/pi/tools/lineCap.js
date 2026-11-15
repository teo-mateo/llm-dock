export const MAX_VISIBLE_LINES = 20

export function cappedSlice(items, expanded) {
  const capped = items.length > MAX_VISIBLE_LINES
  return { capped, shown: capped && !expanded ? items.slice(0, MAX_VISIBLE_LINES) : items }
}
