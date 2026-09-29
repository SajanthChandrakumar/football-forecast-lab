function teamLineup(lineups, team) {
  if (!lineups || !team) return undefined
  if (lineups[team]) return lineups[team]
  const wanted = team.trim().toLocaleLowerCase()
  return Object.entries(lineups).find(([name]) => name.trim().toLocaleLowerCase() === wanted)?.[1]
}

export function lineupState(data, homeTeam, awayTeam) {
  const home = teamLineup(data?.lineups, homeTeam)
  const away = teamLineup(data?.lineups, awayTeam)
  if (home?.starters?.length && away?.starters?.length) {
    return { kind: 'confirmed', home, away, observedAt: data.observed_at, source: data.source }
  }
  return { kind: 'unavailable', message: 'Aufstellungen sind noch nicht veröffentlicht.' }
}
