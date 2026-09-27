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
