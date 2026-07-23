export function pickFence(content) {
  let longest = 0
  const re = /`+/g
  let m
  while ((m = re.exec(content)) !== null) {
    if (m[0].length > longest) longest = m[0].length
  }
  return '`'.repeat(Math.max(3, longest + 1))
}