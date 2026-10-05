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
  if (home?.starters?.length || away?.starters?.length) {
    return { kind: 'unavailable', partial: true, message: 'Nur eine Mannschaft erfasst' }
  }
  const message = data?.reason === 'lineups_not_published'
    ? 'Vom Anbieter noch nicht veröffentlicht'
    : data?.status === 'failed' || ['provider_error', 'fetch_failed'].includes(data?.reason)
      ? 'Abruf fehlgeschlagen'
      : 'Nicht erfasst'
  return { kind: 'unavailable', message }
}
