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

test('uses margin-free bookmaker probabilities before model probabilities', () => {
  const hint = buildMatchHint(match({
    odds: { home: 1.5, draw: 4.5, away: 7 },
    probabilities: { home: 0.1, draw: 0.2, away: 0.7 },
    source_mode: 'odds+elo',
  }))
  assert.equal(hint.source, 'bookmaker')
  assert.equal(hint.sourceLabel, 'Buchmacherquote')
  assert.equal(hint.confidence, 'high')
  assert.ok(hint.probabilities.home > hint.probabilities.draw)
  assert.ok(Math.abs(hint.probabilities.home + hint.probabilities.draw + hint.probabilities.away - 1) < 1e-12)
  assert.equal(hint.summary, 'Die höchste Einzelwahrscheinlichkeit entfällt auf Bayern.')
})

test('keeps probability source and observed time aligned, with missing times explicit', () => {
  const market = buildMatchHint(match({
    odds: { home: 2, draw: 3, away: 4 },
    odds_observed_at: '2026-10-01T12:00:00Z',
    observed_at: '2026-10-02T12:00:00Z',
  }))
  assert.equal(market.observedAt, '2026-10-01T12:00:00Z')

  const model = buildMatchHint(match({
    source_mode: 'elo-only',
    probabilities: { home: 0.5, draw: 0.3, away: 0.2 },
    observed_at: null,
  }))
  assert.equal(model.observedAt, null)
})

test('uses model probabilities only for elo-only matches', () => {
  const hint = buildMatchHint(match({
    probabilities: { home: 0.48, draw: 0.27, away: 0.25 },
    source_mode: 'elo-only',
  }))
  assert.equal(hint.source, 'elo')
  assert.equal(hint.sourceLabel, 'Elo-Modellquote · nicht wettbar')
  assert.equal(hint.confidence, 'medium')
  assert.equal(hint.summary, 'Die höchste Einzelwahrscheinlichkeit entfällt auf Bayern.')
})

test('returns an explicit unavailable hint instead of guessing', () => {
  const hint = buildMatchHint(match({ source_mode: 'unavailable' }))
  assert.deepEqual(hint, {
    available: false,
    summary: 'Für eine verständliche Erklärung fehlen derzeit ausreichende Daten.',
    confidence: 'unavailable',
    confidenceLabel: 'Nicht verfügbar',
    source: 'unavailable',
    sourceLabel: 'Nicht verfügbar',
    probabilities: null,
    observedAt: null,
    reasons: [],
  })
})

test('classifies a narrow probability spread as low confidence', () => {
  const hint = buildMatchHint(match({
    probabilities: { home: 0.39, draw: 0.31, away: 0.30 },
    source_mode: 'elo-only',
  }))
  assert.equal(hint.confidence, 'low')
  assert.equal(hint.summary, 'Die höchste Einzelwahrscheinlichkeit entfällt auf Bayern.')
})

test('describes draw as the most likely single outcome without team reasons', () => {
  const hint = buildMatchHint(match({
    probabilities: { home: 0.3, draw: 0.42, away: 0.28 },
    source_mode: 'elo-only',
    xg_home: 2,
    xg_away: 1,
    home_form: { form: ['W'], on_fire: true },
  }))
  assert.equal(hint.summary, 'Die höchste Einzelwahrscheinlichkeit liegt beim Unentschieden.')
  assert.deepEqual(hint.reasons, [])
})

test('keeps at most two aligned reasons in priority order', () => {
  const hint = buildMatchHint(match({
    probabilities: { home: 0.62, draw: 0.23, away: 0.15 },
    source_mode: 'elo-only',
    xg_home: 1.84,
    xg_away: 1.22,
    home_form: { form: ['W', 'W', 'W'], on_fire: true },
    away_form: { form: ['L'], on_fire: false },
    elo_home_share: 0.64,
  }))
  assert.equal(hint.reasons.length, 2)
  assert.equal(hint.reasons[0], 'Torerwartung: Bayern 1.84 zu Arsenal 1.22.')
  assert.equal(hint.reasons[1], 'Bayern kommt mit der stärkeren aktuellen Form.')
  assert.equal(hint.summary, 'Die höchste Einzelwahrscheinlichkeit entfällt auf Bayern.')
})

test('uses Elo, absences, and knockout context only when their exact conditions match', () => {
  const elo = buildMatchHint(match({
    probabilities: { home: 0.2, draw: 0.25, away: 0.55 }, source_mode: 'elo-only', elo_home_share: 0.35,
  }))
  assert.equal(elo.reasons[0], 'Club-Elo sieht Arsenal bei 65 % im direkten Stärkevergleich.')

  const absencesAndKo = buildMatchHint(match({
    probabilities: { home: 0.6, draw: 0.22, away: 0.18 }, source_mode: 'elo-only',
    lineup_diff: {
      'Bayern Munich': { starters: {}, missing: [] },
      Arsenal: { starters: {}, missing: ['A', 'B'] },
    },
    is_ko_phase: true, first_leg_score: '1:1',
  }))
  assert.deepEqual(absencesAndKo.reasons, [
    'Beim Gegner sind mehr fehlende Spieler gemeldet.',
    'Das Hinspielergebnis kann den Spielverlauf stärker beeinflussen.',
  ])
})
