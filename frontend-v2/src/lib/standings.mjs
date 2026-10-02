export function validUclStandingsRows(rows) {
  if (!Array.isArray(rows) || rows.length !== 36) return null
  const positions = new Set()
  const teams = new Set()
  for (const row of rows) {
    const team = typeof row?.team === 'string' ? row.team.trim() : ''
    if (!team) return null
    if (!Number.isInteger(row.pos) || row.pos < 1 || row.pos > 36 || positions.has(row.pos)) return null
    if (teams.has(team)) return null
    positions.add(row.pos)
    teams.add(team)
  }
  return [...rows].sort((a, b) => a.pos - b.pos)
}

export function validPremierLeagueStandingsRows(rows) {
  if (!Array.isArray(rows) || rows.length !== 20) return null
  const positions = new Set()
  const teams = new Set()
  for (const row of rows) {
    const team = typeof row?.team === 'string' ? row.team.trim() : ''
    if (!team || !Number.isInteger(row.pos) || row.pos < 1 || row.pos > 20) return null
    if (positions.has(row.pos) || teams.has(team)) return null
    positions.add(row.pos)
    teams.add(team)
  }
  return [...rows].sort((a, b) => a.pos - b.pos)
}
