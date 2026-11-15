const CD_PREFIX = /^cd[ \t]+(?:"([^"]*)"|'([^']*)'|([^\s;&]+))[ \t]*(?:&&|;)[ \t]*/

export function splitCdPrefix(command) {
  const match = CD_PREFIX.exec(command)
  if (!match) return { dir: null, command }
  return { dir: match[1] ?? match[2] ?? match[3], command: command.slice(match[0].length).trim() }
}
