import test from 'node:test'
import assert from 'node:assert/strict'
import { chronologicalRecentMatches, formatEloTimestamp } from '../src/lib/team-form.mjs'

test('returns recent archive games in chronological order, with unknown dates first', () => {
  const matches = [
    { playedAt: '2026-10-03T18:00:00Z', score: '2:0' },
    { playedAt: null, score: '1:1' },
    { playedAt: '2026-09-30T18:00:00Z', score: '0:1' },
    { playedAt: '2026-10-02T18:00:00Z', score: '3:1' },
  ]
  assert.deepEqual(chronologicalRecentMatches(matches, 2).map(({ score }) => score), ['3:1', '2:0'])
  assert.deepEqual(chronologicalRecentMatches(matches, 5).map(({ score }) => score), ['1:1', '0:1', '3:1', '2:0'])
})

test('labels Elo history with calendar years and keeps its synthetic start explicit', () => {
  assert.equal(formatEloTimestamp(0), 'Beginn')
  assert.match(formatEloTimestamp(Date.parse('2025-12-31T23:00:00Z') / 1_000), /2026/)
  assert.equal(formatEloTimestamp(Number.NaN), 'Zeitpunkt nicht verfügbar')
})
