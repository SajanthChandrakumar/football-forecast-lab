function validProbabilities(probabilities) {
  if (!probabilities) return false
  const values = ['home', 'draw', 'away'].map((key) => Number(probabilities[key]))
  const total = values.reduce((sum, value) => sum + value, 0)
  return values.every((value) => Number.isFinite(value) && value >= 0 && value <= 1)
    && Math.abs(total - 1) <= 0.01
}

export function performanceEntryKind(entry) {
  if (entry?.post_match_result?.status !== 'completed') return 'pending'
  if (entry?.prediction?.algo_reconstructed === true) return 'reconstructed'

  const frozenAt = Date.parse(entry?.prediction?.frozen_at ?? '')
  const kickoff = Date.parse(entry?.metadata?.commence_time ?? '')
  const actualScore = entry?.post_match_result?.actual_score
  const verified = Number.isFinite(frozenAt)
    && Number.isFinite(kickoff)
    && frozenAt < kickoff
    && validProbabilities(entry?.prediction?.probabilities)
    && /^\d+:\d+$/.test(actualScore ?? '')
  return verified ? 'verified' : 'legacy'
}

export function isOfficialPerformanceEntry(entry) {
  return performanceEntryKind(entry) === 'verified'
}

function brierScore(probabilities, actualScore) {
  const [home, away] = actualScore.split(':').map(Number)
  const outcome = home > away ? 'home' : home < away ? 'away' : 'draw'
  return ['home', 'draw', 'away'].reduce(
    (score, key) => score + (probabilities[key] - (key === outcome ? 1 : 0)) ** 2,
    0,
  )
}

export function officialPerformance(archive, botKeys) {
  const botStats = Object.fromEntries(
    botKeys.map((key) => [key, { pts: 0, tipped: 0, tendency: 0 }]),
  )
  const result = {
    algoTotal: 0,
    algoCount: 0,
    algoTendency: 0,
    legacyCount: 0,
    legacyPoints: 0,
    legacyTendency: 0,
    reconstructedCount: 0,
    reconstructedPoints: 0,
    reconstructedTendency: 0,
    probabilityCount: 0,
    brierScore: null,
    botStats,
  }
  let brierTotal = 0

  for (const entry of Object.values(archive ?? {})) {
    if (entry?.post_match_result?.status !== 'completed') continue
    const kind = performanceEntryKind(entry)

    const algoPoints = entry.post_match_result.algo_points
    if (algoPoints != null) {
      if (kind === 'reconstructed') {
        result.reconstructedCount++
        result.reconstructedPoints += algoPoints
        if (algoPoints >= 5) result.reconstructedTendency++
      } else if (kind === 'verified') {
        result.algoTotal += algoPoints
        result.algoCount++
        if (algoPoints >= 5) result.algoTendency++
      } else {
        result.legacyCount++
        result.legacyPoints += algoPoints
        if (algoPoints >= 5) result.legacyTendency++
      }
    }

    if (kind === 'verified') {
      brierTotal += brierScore(entry.prediction.probabilities, entry.post_match_result.actual_score)
      result.probabilityCount++
    }

    if (kind !== 'verified') continue
    const botPoints = entry.post_match_result.bot_points ?? {}
    for (const key of botKeys) {
      const points = botPoints[key]
      if (points == null) continue
      botStats[key].pts += points
      botStats[key].tipped++
      if (points >= 5) botStats[key].tendency++
    }
  }

  if (result.probabilityCount > 0) {
    result.brierScore = Math.round((brierTotal / result.probabilityCount) * 1_000_000) / 1_000_000
  }

  return result
}
