export function isOfficialPerformanceEntry(entry) {
  return entry?.post_match_result?.status === 'completed'
}

export function officialPerformance(archive, botKeys) {
  const botStats = Object.fromEntries(
    botKeys.map((key) => [key, { pts: 0, tipped: 0, tendency: 0 }]),
  )
  const result = {
    algoTotal: 0,
    algoCount: 0,
    algoTendency: 0,
    reconstructedCount: 0,
    reconstructedPoints: 0,
    reconstructedTendency: 0,
    botStats,
  }

  for (const entry of Object.values(archive ?? {})) {
    if (entry?.post_match_result?.status !== 'completed') continue
    const reconstructed = entry?.prediction?.algo_reconstructed === true

    const algoPoints = entry.post_match_result.algo_points
    if (algoPoints != null) {
      if (reconstructed) {
        result.reconstructedCount++
        result.reconstructedPoints += algoPoints
        if (algoPoints >= 5) result.reconstructedTendency++
      } else {
        result.algoTotal += algoPoints
        result.algoCount++
        if (algoPoints >= 5) result.algoTendency++
      }
    }

    const botPoints = entry.post_match_result.bot_points ?? {}
    for (const key of botKeys) {
      const points = botPoints[key]
      if (points == null) continue
      botStats[key].pts += points
      botStats[key].tipped++
      if (points >= 5) botStats[key].tendency++
    }
  }

  return result
}
