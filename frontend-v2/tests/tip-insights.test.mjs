import test from 'node:test'
import assert from 'node:assert/strict'
import { rankedTipInsights, recentFormSummary, matchLoadSummary } from '../src/lib/tip-insights.mjs'

test('ranks tips by expected points while showing each exact-score chance separately', () => {
  const tips = [{ Tipp: '2:0', xP: 5.06 }, { Tipp: '1:0', xP: 4.9 }, { Tipp: '3:1', xP: 4.86 }]
  const matrix = { 1: { 0: 0.076 }, 2: { 0: 0.137 }, 3: { 1: 0.072 } }
  assert.deepEqual(rankedTipInsights(tips, matrix), [
    { tip: '2:0', expectedPoints: 5.06, exactChance: 0.137 },
    { tip: '1:0', expectedPoints: 4.9, exactChance: 0.076 },
    { tip: '3:1', expectedPoints: 4.86, exactChance: 0.072 },
  ])
})

test('does not invent exact-score chances when the matrix is missing', () => {
  assert.deepEqual(rankedTipInsights([{ Tipp: '2:0', xP: 5 }]), [
    { tip: '2:0', expectedPoints: 5, exactChance: null },
  ])
})

test('summarizes five competitive results in plain language', () => {
  assert.equal(recentFormSummary({ form: ['L', 'W', 'W', 'W', 'W'] }), 'Letzte 5: 4 Siege, 1 Niederlage')
  assert.equal(recentFormSummary({ form: [], status: 'unavailable' }), 'Form nicht verfügbar')
})

test('match load uses only recorded games before kickoff', () => {
  const form = { observed_at: '2026-10-13T18:00:00Z', matches: [
    { played_at: '2026-10-16T18:00:00Z' },
    { played_at: '2026-10-12T18:00:00Z' },
    { played_at: '2026-10-08T18:00:00Z' },
    { played_at: '2026-09-20T18:00:00Z' },
  ] }
  assert.equal(
    matchLoadSummary(form, '2026-10-14T18:00:00Z'),
    '2 Tage Pause · 2 erfasste Spiele in 14 Tagen',
  )
  assert.equal(matchLoadSummary(form, 'invalid'), null)
  assert.equal(matchLoadSummary({ matches: [] }, '2026-10-14T18:00:00Z'), null)
})

test('match load does not project stale form weeks into the future', () => {
  const form = {
    observed_at: '2026-09-26T08:00:00Z',
    matches: [{ played_at: '2026-09-18T18:45:00Z' }],
  }
  assert.equal(matchLoadSummary(form, '2026-10-13T16:45:00Z'), null)
})
