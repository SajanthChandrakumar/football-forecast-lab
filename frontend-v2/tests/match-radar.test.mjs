import test from 'node:test'
import assert from 'node:assert/strict'
import { buildMatchdayRadar } from '../src/lib/matchRadar.ts'

const match = (id, time, overrides = {}) => ({
  id, home_team: `Home ${id}`, away_team: `Away ${id}`, home_disp: `Heim ${id}`, away_disp: `Gast ${id}`,
  top_tip: '2:1', max_xp: 4.2, source_mode: 'elo-only', probabilities: { home: 0.62, draw: 0.22, away: 0.16 },
  raw_match: { commence_time: time }, ...overrides,
})

test('limits the radar to the next 72-hour matchday window', () => {
  const radar = buildMatchdayRadar([
    match('late', '2026-10-01T18:00:00Z'), match('first', '2026-09-22T18:00:00Z'),
    match('second', '2026-09-24T20:00:00Z'), match('played', '2026-09-22T20:00:00Z', { completed: true, actual_score: '1:0' }),
  ], Date.parse('2026-09-22T12:00:00Z'))
  assert.deepEqual(radar.matches.map(({ match: item }) => item.id), ['first', 'second'])
})

test('ignores elapsed fixtures that are still marked incomplete', () => {
  const radar = buildMatchdayRadar([match('stale', '2026-09-22T10:00:00Z'), match('next', '2026-09-23T18:00:00Z')], Date.parse('2026-09-22T12:00:00Z'))
  assert.deepEqual(radar.matches.map(({ match: item }) => item.id), ['next'])
})

test('prioritizes a real model-market gap as a surprise alert', () => {
  const radar = buildMatchdayRadar([match('edge', '2026-09-22T18:00:00Z', {
    source_mode: 'odds+elo', odds: { home: 2.8, draw: 3.2, away: 2.3 }, probabilities: { home: 0.56, draw: 0.24, away: 0.2 },
    elo_home_share: 0.62, market_home_share: 0.45, edge_home: 0.17,
  })], Date.parse('2026-09-22T12:00:00Z'))
  assert.equal(radar.matches[0].category, 'surprise')
  assert.equal(radar.counts.surprise, 1)
  assert.match(radar.matches[0].reason, /Heim edge.*stärker.*Markt/)
})

test('separates high-confidence tips from open and unavailable matches', () => {
  const radar = buildMatchdayRadar([
    match('safe', '2026-09-22T18:00:00Z'),
    match('open', '2026-09-22T20:00:00Z', { probabilities: { home: 0.39, draw: 0.31, away: 0.3 } }),
    match('missing', '2026-09-23T18:00:00Z', { source_mode: 'unavailable', probabilities: null, top_tip: 'N/A' }),
  ], Date.parse('2026-09-22T12:00:00Z'))
  assert.deepEqual(radar.counts, { safe: 1, open: 2, surprise: 0 })
  assert.deepEqual(radar.matches.map(({ category }) => category), ['safe', 'open', 'open'])
  assert.match(radar.matches[2].reason, /Noch nicht genug Daten/)
  assert.equal(radar.tipCard, ['Spieltag-Radar', 'Heim safe – Gast safe: 2:1', 'Heim open – Gast open: 2:1', 'Heim missing – Gast missing: –'].join('\n'))
})
