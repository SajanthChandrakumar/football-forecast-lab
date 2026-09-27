import test from 'node:test'
import assert from 'node:assert/strict'
import { rankedTipInsights, recentFormSummary } from '../src/lib/tip-insights.mjs'

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
