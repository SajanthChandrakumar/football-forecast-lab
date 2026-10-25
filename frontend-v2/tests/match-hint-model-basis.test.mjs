import test from 'node:test'
import assert from 'node:assert/strict'
import { buildMatchHint } from '../src/lib/matchHint.ts'

const match = (overrides = {}) => ({
  id: 'm1',
  home_team: 'Bayern Munich',
  away_team: 'Arsenal',
  home_disp: 'Bayern',
  away_disp: 'Arsenal',
  top_tip: '2:1',
  max_xp: 4.2,
  raw_match: {},
  ...overrides,
})

const modelBasis = (overrides, requireFreshInputs = false) =>
  buildMatchHint(match(overrides), Date.parse('2026-10-24T12:00:00Z'), requireFreshInputs, { basis: 'model' })

test('model basis uses displayed odds plus Elo probabilities instead of market odds', () => {
  const hint = modelBasis({
    source_mode: 'odds+elo',
    odds: { home: 1.5, draw: 4.5, away: 7 },
    probabilities: { home: 0.46, draw: 0.31, away: 0.23 },
    observed_at: '2026-10-24T11:00:00Z',
  })

  assert.equal(hint.source, 'model')
  assert.equal(hint.sourceLabel, 'Modellprognose · Buchmacherquoten + Elo')
  assert.deepEqual(hint.probabilities, { home: 0.46, draw: 0.31, away: 0.23 })
  assert.equal(hint.observedAt, '2026-10-24T11:00:00Z')
})

test('model basis accepts odds-only and Elo-only probabilities with distinct provenance', () => {
  const oddsOnly = modelBasis({
    source_mode: 'odds-only',
    odds: { home: 2, draw: 3, away: 4 },
    probabilities: { home: 0.57, draw: 0.24, away: 0.19 },
  })
  const eloOnly = modelBasis({
    source_mode: 'elo-only',
    probabilities: { home: 0.48, draw: 0.27, away: 0.25 },
  })

  assert.equal(oddsOnly.sourceLabel, 'Modellprognose · Buchmacherquoten')
  assert.deepEqual(oddsOnly.probabilities, { home: 0.57, draw: 0.24, away: 0.19 })
  assert.equal(eloOnly.sourceLabel, 'Modellprognose · Elo')
  assert.deepEqual(eloOnly.probabilities, { home: 0.48, draw: 0.27, away: 0.25 })
})

test('model basis keeps valid legacy probabilities when source mode is missing', () => {
  const hint = modelBasis({
    odds: { home: 1.5, draw: 4.5, away: 7 },
    probabilities: { home: 0.62, draw: 0.23, away: 0.15 },
    observed_at: '2026-10-24T11:00:00Z',
  })

  assert.equal(hint.available, true)
  assert.equal(hint.source, 'model')
  assert.equal(hint.sourceLabel, 'Modellprognose · Quelle nicht belegt')
  assert.deepEqual(hint.probabilities, { home: 0.62, draw: 0.23, away: 0.15 })
  assert.equal(hint.observedAt, '2026-10-24T11:00:00Z')
})

test('model basis reports unavailable instead of falling back to live odds', () => {
  const hint = modelBasis({
    source_mode: 'odds-only',
    odds: { home: 1.5, draw: 4.5, away: 7 },
    probabilities: null,
  })

  assert.equal(hint.available, false)
  assert.equal(hint.source, 'unavailable')
  assert.equal(hint.probabilities, null)
})

test('model basis keeps stale input confidence limits', () => {
  const hint = modelBasis({
    source_mode: 'odds+elo',
    probabilities: { home: 0.62, draw: 0.23, away: 0.15 },
    input_provenance: { odds: { status: 'fresh', observed_at: '2026-10-24T11:00:00Z' } },
  }, true)

  assert.equal(hint.confidence, 'medium')
  assert.match(hint.freshnessWarning, /Elo-Zeitpunkt fehlt/)
})
