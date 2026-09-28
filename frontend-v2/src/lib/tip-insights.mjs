export function rankedTipInsights(tips = [], matrix, limit = 3) {
  return tips
    .filter((item) => typeof item?.Tipp === 'string' && Number.isFinite(item.xP))
    .sort((a, b) => b.xP - a.xP)
    .slice(0, limit)
    .map(({ Tipp, xP }) => {
      const [home, away] = Tipp.split(':').map(Number)
      const chance = matrix?.[home]?.[away]
      return {
        tip: Tipp,
        expectedPoints: xP,
        exactChance: Number.isFinite(chance) && chance >= 0 ? chance : null,
      }
    })
}

export function recentFormSummary(form) {
  const results = form?.form?.slice(-5) ?? []
  if (!results.length) return 'Form nicht verfügbar'
  const labels = [
    ['W', 'Sieg', 'Siege'],
    ['D', 'Unentschieden', 'Unentschieden'],
    ['L', 'Niederlage', 'Niederlagen'],
  ]
  const parts = labels.flatMap(([key, singular, plural]) => {
    const count = results.filter((result) => result === key).length
    return count ? [`${count} ${count === 1 ? singular : plural}`] : []
  })
  return `Letzte ${results.length}: ${parts.join(', ')}`
}

export function matchLoadSummary(form, kickoff) {
  const kickoffTime = Date.parse(kickoff)
  const observedTime = Date.parse(form?.observed_at)
  const day = 24 * 60 * 60 * 1000
  if (!Number.isFinite(kickoffTime) || !Number.isFinite(observedTime)
    || observedTime > kickoffTime || kickoffTime - observedTime > 2 * day
    || !Array.isArray(form?.matches)) return null

  const played = form.matches
    .map((match) => Date.parse(match?.played_at))
    .filter((time) => Number.isFinite(time) && time < kickoffTime)
  if (!played.length) return null

  const restDays = Math.floor((kickoffTime - Math.max(...played)) / day)
  const recentGames = played.filter((time) => time >= kickoffTime - 14 * day).length
  const rest = restDays === 0 ? 'Unter 1 Tag Pause' : `${restDays} ${restDays === 1 ? 'Tag' : 'Tage'} Pause`
  return `${rest} · ${recentGames} erfasste ${recentGames === 1 ? 'Spiel' : 'Spiele'} in 14 Tagen`
}
