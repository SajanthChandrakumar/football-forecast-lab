import { groupFixturesByRound } from './fixture-rounds.mjs'

export function rankUpcomingValueBets(matches = [], now = Date.now(), period = 'next') {
  const cutoff = now instanceof Date ? now.getTime() : now
  const upcoming = matches.filter((match) => {
    const kickoff = Date.parse(match.raw_match?.commence_time ?? '')
    return Number.isFinite(kickoff) && kickoff > cutoff && !match.completed && !match.actual_score && match.max_xp > 0
  })
  const selected = period === 'all' ? upcoming : groupFixturesByRound(upcoming)[0]?.matches ?? []
  return [...selected].sort((a, b) => b.max_xp - a.max_xp)
}
