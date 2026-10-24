import test from 'node:test'
import assert from 'node:assert/strict'
import { chronologicalOddsHistory, oddsHistoryChartRows } from '../src/features/detail/odds-history.mjs'

test('odds history uses observed timestamps in chronological chart order', () => {
  const observations = [
    { observed_at: '2026-10-24T12:00:00Z', probabilities: { home: 0.6, draw: 0.2, away: 0.2 } },
    { observed_at: '2026-10-24T06:30:00Z', probabilities: { home: 0.4, draw: 0.3, away: 0.3 } },
    { observed_at: 'not-a-date', probabilities: { home: 1, draw: 0, away: 0 } },
  ]
  const rows = oddsHistoryChartRows(observations)
  assert.deepEqual(rows.map((row) => row.observedTimestamp), [
    Date.parse('2026-10-24T06:30:00Z'), Date.parse('2026-10-24T12:00:00Z'),
  ])
  assert.deepEqual(chronologicalOddsHistory(observations).map(({ observed_at }) => observed_at), [
    '2026-10-24T06:30:00Z', '2026-10-24T12:00:00Z',
  ])
})
