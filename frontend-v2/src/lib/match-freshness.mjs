const MAX_AGE_MS = 24 * 60 * 60 * 1000

export function modelInputFreshness(match, now = Date.now()) {
  const mode = match?.source_mode
  const inputs = mode === 'odds+elo' ? ['odds', 'elo']
    : mode === 'odds-only' ? ['odds']
      : mode === 'elo-only' ? ['elo'] : []
  if (!inputs.length) return { status: 'unknown', message: 'Verwendete Datenquellen sind nicht bestätigt.' }

  const provenance = match.input_provenance ?? match.provenance ?? {}
  let stale = false
  for (const input of inputs) {
    const metadata = provenance[input] ?? {}
    if (metadata.status === 'failed') return { status: 'failed', message: `${input === 'odds' ? 'Quoten' : 'Elo'}-Abruf fehlgeschlagen.` }
    if (metadata.status === 'stale') stale = true
    const rawTimestamp = metadata.observed_at ?? (input === 'odds' ? match.odds_observed_at : match.observed_at)
    const observedAt = typeof rawTimestamp === 'string' ? Date.parse(rawTimestamp) : NaN
    if (!Number.isFinite(observedAt) || observedAt > now) {
      return { status: 'unknown', message: `${input === 'odds' ? 'Quoten' : 'Elo'}-Zeitpunkt fehlt oder liegt in der Zukunft.` }
    }
    if (now - observedAt > MAX_AGE_MS) stale = true
  }
  return stale
    ? { status: 'stale', message: 'Mindestens eine verwendete Quelle ist älter als 24 Stunden.' }
    : { status: 'fresh', message: '' }
}
