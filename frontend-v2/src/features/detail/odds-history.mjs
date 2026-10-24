export function chronologicalOddsHistory(observations = []) {
  return observations
    .filter((point) => Number.isFinite(Date.parse(point?.observed_at ?? '')))
    .slice()
    .sort((a, b) => Date.parse(a.observed_at) - Date.parse(b.observed_at))
}

export function oddsHistoryChartRows(observations = []) {
  return chronologicalOddsHistory(observations).map((point) => ({
    observedTimestamp: Date.parse(point.observed_at),
    Heim: point.probabilities.home * 100,
    Remis: point.probabilities.draw * 100,
    Auswärts: point.probabilities.away * 100,
  }))
}
