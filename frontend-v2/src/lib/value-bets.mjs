export function rankUpcomingValueBets(matches = [], now = Date.now()) {
  const cutoff = now instanceof Date ? now.getTime() : now
  return matches
    .filter((match) => {
      const kickoff = Date.parse(match.raw_match?.commence_time ?? '')
      return Number.isFinite(kickoff)
        && kickoff > cutoff
        && !match.completed
        && !match.actual_score
        && match.max_xp > 0
    })
    .sort((a, b) => b.max_xp - a.max_xp)
}
