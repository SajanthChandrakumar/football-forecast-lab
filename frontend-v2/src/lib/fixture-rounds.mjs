const KNOCKOUT_LABELS = [
  [/round of 32|last 32|sechzehntelfinale/i, 'Sechzehntelfinale'],
  [/round of 16|last 16|achtelfinale/i, 'Achtelfinale'],
  [/quarter.?final|viertelfinale/i, 'Viertelfinale'],
  [/semi.?final|halbfinale/i, 'Halbfinale'],
  [/^final$|^finale$/i, 'Finale'],
]

function weekStart(timestamp) {
  const date = new Date(timestamp)
  date.setUTCHours(0, 0, 0, 0)
  date.setUTCDate(date.getUTCDate() - ((date.getUTCDay() + 6) % 7))
  return date.toISOString().slice(0, 10)
}

export function groupFixturesByRound(matches) {
  const groups = new Map()
  for (const match of matches) {
    const kickoff = Date.parse(match.raw_match?.commence_time ?? '')
    const round = String(match.raw_match?.round ?? '')
    const namedRound = KNOCKOUT_LABELS.find(([pattern]) => pattern.test(round))?.[1]
    const key = namedRound ? `knockout:${namedRound}` : Number.isFinite(kickoff) ? `week:${weekStart(kickoff)}` : 'undated'
    if (!groups.has(key)) groups.set(key, { key, label: namedRound ?? '', matches: [], firstKickoff: Infinity, lastKickoff: -Infinity })
    const group = groups.get(key)
    group.matches.push(match)
    if (Number.isFinite(kickoff)) {
      group.firstKickoff = Math.min(group.firstKickoff, kickoff)
      group.lastKickoff = Math.max(group.lastKickoff, kickoff)
    }
  }

  const sorted = [...groups.values()].sort((a, b) => a.firstKickoff - b.firstKickoff)
  let week = 0
  for (const group of sorted) {
    group.matches.sort((a, b) => Date.parse(a.raw_match?.commence_time ?? '') - Date.parse(b.raw_match?.commence_time ?? ''))
    if (group.key.startsWith('week:')) group.label = `Spielwoche ${++week}`
    if (group.key === 'undated') group.label = 'Anstoß offen'
  }
  return sorted
}
