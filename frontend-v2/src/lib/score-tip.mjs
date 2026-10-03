const scorePattern = /^(\d+):(\d+)$/

export function parseScoreFields(value) {
  const match = typeof value === 'string' ? scorePattern.exec(value.trim()) : null
  return match ? { home: match[1], away: match[2] } : null
}

export function formatScoreFields(home, away) {
  if (!/^\d+$/.test(home) || !/^\d+$/.test(away)) return null
  const homeGoals = Number(home)
  const awayGoals = Number(away)
  if (!Number.isSafeInteger(homeGoals) || !Number.isSafeInteger(awayGoals)) return null
  return `${homeGoals}:${awayGoals}`
}
