const ROWS = [
  ['Angriff', /^(F|CF|ST|LW|RW)/],
  ['Mittelfeld', /^(M|CM|DM|AM|LM|RM)/],
  ['Abwehr', /^(D|CD|CB|LB|RB|WB)/],
  ['Tor', /^(G|GK)/],
]

export function lineupRows(players = []) {
  const grouped = new Map(ROWS.map(([role]) => [role, []]))
  const other = []
  for (const player of players) {
    const position = String(player?.position ?? '').toUpperCase()
    const row = ROWS.find(([, pattern]) => pattern.test(position))
    ;(row ? grouped.get(row[0]) : other).push(player)
  }
  return [
    ...ROWS.flatMap(([role]) => grouped.get(role).length ? [{ role, players: grouped.get(role) }] : []),
    ...(other.length ? [{ role: 'Weitere', players: other }] : []),
  ]
}
