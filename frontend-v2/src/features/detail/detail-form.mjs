import { formatObservedAt } from '../../lib/observed-at.mjs'
import { formatScoreFields, parseScoreFields } from '../../lib/score-tip.mjs'
export { formatObservedAt }
export { formatScoreFields, parseScoreFields }

const scorePattern = /^(\d+):(\d+)$/
const statusLabels = {
  available: 'Verfügbar',
  failed: 'Fehler',
  fresh: 'Aktuell',
  partial: 'Teilweise verfügbar',
  stale: 'Möglicherweise veraltet',
  unavailable: 'Nicht verfügbar',
}

export function parseTipCountRows(rows) {
  const counts = {}
  for (const { tip, count } of rows) {
    const score = tip.trim()
    const amount = count.trim()
    if (!score && !amount) continue
    if (!scorePattern.test(score) || !/^\d+$/.test(amount)) return null

    const nextCount = (counts[score] ?? 0) + Number(amount)
    if (!Number.isSafeInteger(nextCount)) return null
    if (nextCount > 0) counts[score] = nextCount
    else delete counts[score]
  }
  return counts
}

export function formatDataStatus(status, observedAt, now = Date.now()) {
  if (!status) return 'Status nicht angegeben'
  if (status.toLowerCase() === 'fresh') {
    const timestamp = Date.parse(observedAt ?? '')
    if (!Number.isFinite(timestamp)) return 'Zeitpunkt nicht bestätigt'
    if (now - timestamp > 86_400_000) return 'Älterer Datenstand'
  }
  return statusLabels[status.toLowerCase()] ?? status.replaceAll('_', ' ')
}
