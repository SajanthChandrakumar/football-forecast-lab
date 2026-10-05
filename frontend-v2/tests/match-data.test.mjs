import test from 'node:test'
import assert from 'node:assert/strict'
import { buildMatchDataStatus } from '../src/lib/match-data.ts'

const now = Date.parse('2026-10-04T12:00:00Z')
const observed = '2026-10-04T10:00:00Z'
const match = (extra = {}) => ({
  id: 'one', home_team: 'Arsenal', away_team: 'Chelsea', home_disp: 'Arsenal', away_disp: 'Chelsea',
  top_tip: '2:1', max_xp: 4, raw_match: {}, source_mode: 'odds+elo',
  odds: { home: 2, draw: 3.5, away: 4 }, odds_observed_at: observed,
  input_provenance: {
    odds: { status: 'fresh', source: 'odds_api', observed_at: observed },
    elo: { status: 'fresh', source: 'clubelo', observed_at: observed },
  }, ...extra,
})

test('keeps odds and Elo ages independent from a new prediction time', () => {
  const data = buildMatchDataStatus(match({ observed_at: '2026-10-04T12:00:00Z', input_provenance: {
    odds: { status: 'fresh', source: 'api_football', observed_at: '2026-10-01T10:00:00Z' },
    elo: { status: 'fresh', source: 'clubelo', observed_at: observed },
  } }), now)
  assert.equal(data.status, 'stale')
  assert.equal(data.rows[0].status, 'stale')
  assert.equal(data.rows[0].source, 'API-Football')
  assert.equal(data.rows[0].observedAt, '2026-10-01T10:00:00Z')
  assert.equal(data.rows[1].status, 'fresh')
})

test('never uses the calculation time as proof of Elo freshness', () => {
  const data = buildMatchDataStatus(match({ input_provenance: {}, observed_at: observed, status: 'fresh' }), now)
  assert.equal(data.status, 'partial')
  assert.equal(data.rows[1].status, 'unknown')
  assert.equal(data.rows[1].observedAt, null)
  assert.match(data.explanation, /Aktualität/)
})

test('explains an Elo-only suggestion without fabricating bookmaker data', () => {
  const data = buildMatchDataStatus(match({ odds: undefined, odds_observed_at: null, source_mode: 'elo-only' }), now)
  assert.equal(data.status, 'partial')
  assert.equal(data.rows[0].status, 'unavailable')
  assert.match(data.explanation, /nur Elo/)
  assert.match(data.explanation, /Buchmacherquoten fehlen/)
})

test('does not mark absent lineups as unpublished without provider evidence', () => {
  const data = buildMatchDataStatus(match(), now)
  assert.equal(data.status, 'fresh')
  assert.equal(data.rows[2].status, 'unavailable')
  assert.match(data.rows[2].message, /Nicht erfasst/)
  assert.doesNotMatch(data.rows[2].message, /nicht veröffentlicht/)
  const unpublished = buildMatchDataStatus(match({ match_intelligence: { status: 'unavailable', reason: 'lineups_not_published' } }), now)
  assert.match(unpublished.rows[2].message, /noch nicht veröffentlicht/)
})

test('retains source failure and partial lineup evidence', () => {
  const data = buildMatchDataStatus(match({ input_provenance: {
    odds: { status: 'failed', source: 'odds_api', observed_at: observed },
    elo: { status: 'stale', source: 'clubelo', observed_at: observed },
  }, match_intelligence: { status: 'fresh', source: 'espn', observed_at: observed, lineups: {
    Arsenal: { starters: [{ name: 'Player' }], substitutes: [] },
  } } }), now)
  assert.equal(data.rows[0].status, 'failed')
  assert.equal(data.status, 'stale')
  assert.equal(data.rows[2].status, 'partial')
  assert.match(data.rows[2].message, /eine Mannschaft/)
})

test('future or invalid source timestamps cannot certify current data', () => {
  const data = buildMatchDataStatus(match({ input_provenance: {
    odds: { status: 'fresh', observed_at: 'invalid' },
    elo: { status: 'fresh', observed_at: '2026-10-05T10:00:00Z' },
  } }), now)
  assert.equal(data.rows[0].status, 'unknown')
  assert.equal(data.rows[1].status, 'unknown')
  assert.equal(data.rows[1].observedAt, null)
  assert.equal(data.status, 'partial')
})

test('does not trust unused provenance as evidence of available Elo', () => {
  const data = buildMatchDataStatus(match({ source_mode: 'odds-only' }), now)
  assert.equal(data.rows[1].status, 'unavailable')
  assert.match(data.explanation, /Elo/)
  const none = buildMatchDataStatus(match({ odds: undefined, source_mode: 'unavailable', top_tip: 'N/A' }), now)
  assert.equal(none.status, 'unavailable')
})


test('uses the displayed prediction inputs instead of the cached match inputs', () => {
  const prediction = {
    model_tip: '3:0', source_mode: 'elo-only', observed_at: observed,
    input_provenance: { elo: { source: 'elo', status: 'fresh' } },
  }
  const data = buildMatchDataStatus(match(), now, prediction)
  assert.equal(data.rows[0].status, 'unavailable')
  assert.equal(data.rows[0].observedAt, null)
  assert.equal(data.rows[1].source, 'Elo-Daten')
  assert.equal(data.rows[1].status, 'unknown')
  assert.equal(data.rows[1].observedAt, null)
  assert.match(data.explanation, /nur Elo/)
})

test('keeps matchup lineups while using the new prediction provenance', () => {
  const data = buildMatchDataStatus(match({ match_intelligence: {
    status: 'failed', source: 'espn', reason: 'provider_error',
  } }), now, { model_tip: '1:0', source_mode: 'odds-only', input_provenance: {
    odds: { source: 'api_football', status: 'stale', observed_at: '2026-10-01T10:00:00Z' },
  } })
  assert.equal(data.rows[0].source, 'API-Football')
  assert.equal(data.rows[0].status, 'stale')
  assert.equal(data.rows[1].status, 'unavailable')
  assert.equal(data.rows[2].status, 'failed')
})
