import test from 'node:test'
import assert from 'node:assert/strict'
import { matchFormInsights, rankedTipInsights, recentFormSummary, matchLoadSummary, playerFormStatusMessage, playerFormSummary, teamHistoryAnalysis, teamHistoryMetrics, scoreProbabilitySummary } from '../src/lib/tip-insights.mjs'

test('explains likely exact scores separately from the points-optimized tip', () => {
  const matrix = { 0: { 0: 0.08, 1: 0.04 }, 1: { 0: 0.1, 1: 0.125 }, 2: { 1: 0.084 } }
  assert.deepEqual(scoreProbabilitySummary(matrix, '2:1'), {
    topScores: [{ tip: '1:1', chance: 0.125 }, { tip: '1:0', chance: 0.1 }, { tip: '2:1', chance: 0.084 }],
    modelTipChance: 0.084,
  })
  assert.equal(scoreProbabilitySummary(undefined, '2:1'), null)
})

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

test('summarizes up to ten competitive results', () => {
  assert.equal(
    recentFormSummary({ form: ['W', 'W', 'D', 'L', 'W', 'D', 'W', 'L', 'W', 'W'] }),
    'Letzte 10: 6 Siege, 2 Unentschieden, 2 Niederlagen',
  )
})

test('turns scored history into a plain-language trend', () => {
  const matches = Array.from({ length: 10 }, (_, index) => ({
    result: index < 7 ? 'W' : index < 9 ? 'D' : 'L',
    goals_for: index < 7 ? 2 : 1,
    goals_against: index === 9 ? 2 : 0,
  }))

  assert.equal(
    teamHistoryAnalysis({ matches }),
    'Starke Form · 7 Siege aus 10 · Ø 1.7:0.2 Tore',
  )
})

test('calculates transparent team metrics from recorded match scores', () => {
  const matches = [
    { goals_for: 2, goals_against: 0 },
    { goals_for: 1, goals_against: 1 },
    { goals_for: 0, goals_against: 1 },
    { goals_for: 3, goals_against: 2 },
    { goals_for: 2, goals_against: 0 },
  ]

  assert.deepEqual(teamHistoryMetrics({ matches }), {
    matches: 5,
    goalsFor: 8,
    goalsAgainst: 4,
    averageFor: 1.6,
    averageAgainst: 0.8,
    cleanSheets: 2,
    bothTeamsScored: 2,
  })
})

test('explains the observed form and scoring matchup without guessing missing results', () => {
  const home = { matches: [
    { result: 'L', goals_for: 1, goals_against: 2 },
    { result: 'D', goals_for: 2, goals_against: 2 },
    { result: 'W', goals_for: 3, goals_against: 2 },
    { result: 'L', goals_for: 0, goals_against: 1 },
    { result: 'L', goals_for: 1, goals_against: 2 },
  ] }
  const away = { matches: [
    { result: 'D', goals_for: 2, goals_against: 2 },
    { result: 'D', goals_for: 1, goals_against: 1 },
    { result: 'W', goals_for: 3, goals_against: 1 },
    { result: 'W', goals_for: 2, goals_against: 0 },
    { result: 'W', goals_for: 4, goals_against: 0 },
  ] }
  assert.deepEqual(matchFormInsights('Lens', home, 'Sporting CP', away), [
    {
      kind: 'form',
      title: 'Sporting CP zuletzt in besserer Form',
      detail: '3 Siege in 5 erfassten Spielen. Lens gewann 1 von 5.',
    },
    {
      kind: 'goals',
      title: 'Sporting CP trifft regelmäßig',
      detail: 'Tor in 5 von 5 Spielen. Lens kassierte in 5 von 5 ein Gegentor.',
    },
  ])
  assert.deepEqual(matchFormInsights('Lens', home, 'Sporting CP', { matches: [] }), [])
})

test('describes player contributions without an opaque score', () => {
  assert.equal(
    playerFormSummary({ goals: 3, assists: 1, appearances: 3 }),
    '3 Tore · 1 Assist · 3 Einsätze',
  )
  assert.equal(
    playerFormSummary({ goals: 1, assists: 2, appearances: 1 }),
    '1 Tor · 2 Assists · 1 Einsatz',
  )
  assert.equal(
    playerFormSummary({ goals: 1, assists: null, appearances: 1 }),
    '1 Tor · 1 Einsatz',
  )
})

test('distinguishes missing player samples from no recorded contributions', () => {
  assert.equal(
    playerFormStatusMessage({ matches_sampled: 2, minimum_matches: 3, reason: 'insufficient_sample' }),
    'Noch zu wenig echte Spielerdaten (2 von 3 Spielen archiviert).',
  )
  assert.equal(
    playerFormStatusMessage({ matches_sampled: 3, minimum_matches: 3, reason: 'no_contributions' }),
    'In 3 archivierten Spielen wurden keine individuellen Tore oder Assists erfasst.',
  )
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
