import { fixtureStatus, sharedTipIsOpen } from './fixture-status.mjs'

export const TIP_BATCH_LIMIT = 18
export const TIP_SAVE_CONCURRENCY = 3

export function normalizeScoreTip(value) {
  if (typeof value !== 'string' || !/^(\d{1,2}):(\d{1,2})$/.test(value)) return null
  const [home, away] = value.split(':').map(Number)
  return home <= 20 && away <= 20 ? `${home}:${away}` : null
}

export function isValidScoreTip(value) {
  return normalizeScoreTip(value) !== null
}

export function buildAssistantRows(matches, archive, drafts, savedOverrides, now = Date.now()) {
  return matches.map((match) => {
    const savedTip = savedOverrides[match.id]
      ?? archive?.[match.id]?.prediction?.user_tip
      ?? ''
    const status = fixtureStatus(match, now)
    const unavailable = match.source_mode === 'unavailable'
      || [match.source_status, match.status].some((value) => value === 'unavailable' || value === 'failed')
    const suggestion = status === 'played' || unavailable ? '' : normalizeScoreTip(match.top_tip) ?? ''
    const sourceLabel = ({
      'odds+elo': 'Buchmacher + Elo',
      'elo-only': 'Elo',
      'odds-only': 'Quote',
    })[match.source_mode] ?? (unavailable ? 'Keine Prognose verfügbar' : 'Quelle unbekannt')
    const value = Object.hasOwn(drafts, match.id) ? drafts[match.id] : savedTip || suggestion
    const kickoff = Date.parse(match.raw_match?.commence_time ?? '')
    const observedAt = typeof match.observed_at === 'string' && Number.isFinite(Date.parse(match.observed_at))
      ? match.observed_at
      : ''

    return {
      match,
      status,
      kickoff,
      savedTip,
      suggestion,
      sourceLabel,
      stale: match.status === 'stale' || match.source_status === 'stale',
      observedAt,
      value,
      editable: status === 'upcoming' && sharedTipIsOpen(match.raw_match?.commence_time, now),
      saved: Boolean(normalizeScoreTip(savedTip)) && normalizeScoreTip(value) === normalizeScoreTip(savedTip),
      changed: normalizeScoreTip(value) !== normalizeScoreTip(savedTip),
      touched: Object.hasOwn(drafts, match.id),
    }
  })
}

export function getSaveCandidates(rows) {
  return rows
    .filter((row) => row.editable && row.changed && normalizeScoreTip(row.value) !== null)
    .map(({ match, value }) => ({ match, tip: normalizeScoreTip(value) }))
}

export async function saveTipBatch(items, save) {
  const batch = items.slice(0, TIP_BATCH_LIMIT)
  const results = new Array(batch.length)
  let next = 0

  await Promise.all(Array.from({ length: Math.min(TIP_SAVE_CONCURRENCY, batch.length) }, async () => {
    while (next < batch.length) {
      const index = next++
      const item = batch[index]
      try {
        await save(item)
        results[index] = { item, ok: true }
      } catch (error) {
        results[index] = { item, ok: false, error: error instanceof Error ? error.message : String(error) }
      }
    }
  }))

  return { results, remaining: items.length - batch.length }
}
