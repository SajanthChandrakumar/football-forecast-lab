export function fixtureStatus(match, now = Date.now()) {
  if (match.completed || match.actual_score) return 'played'
  const kickoff = Date.parse(match.raw_match?.commence_time ?? '')
  if (!Number.isFinite(kickoff)) return 'unscheduled'
  return kickoff <= now ? 'pending' : 'upcoming'
}

export function preferredFixtureTab(counts) {
  return ['upcoming', 'played', 'pending', 'unscheduled'].find((tab) => counts[tab] > 0) ?? 'upcoming'
}

export function sharedTipIsOpen(commenceTime, now = Date.now()) {
  const kickoff = Date.parse(commenceTime ?? '')
  return Number.isFinite(kickoff) && now < kickoff - 5 * 60_000
}
