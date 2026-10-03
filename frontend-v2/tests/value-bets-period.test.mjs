import test from 'node:test'
import assert from 'node:assert/strict'
import { rankUpcomingValueBets } from '../src/lib/value-bets.mjs'

const now = Date.parse('2026-10-02T12:00:00Z')
const fixture = (id, date, xp) => ({id, raw_match: {commence_time: date}, max_xp: xp})
const matches = [fixture('far', '2027-01-19T20:00:00Z', 9), fixture('next', '2026-10-13T16:45:00Z', 3), fixture('same-week', '2026-10-14T19:00:00Z', 4), fixture('later', '2026-10-20T19:00:00Z', 5)]

test('defaults to the next available week rather than promoting a distant game', () => {
  assert.deepEqual(rankUpcomingValueBets(matches, now).map(m => m.id), ['same-week', 'next'])
})
test('allows all upcoming games explicitly and never includes completed games', () => {
  assert.deepEqual(rankUpcomingValueBets([...matches, {...fixture('played','2026-10-13T19:00:00Z',20), completed:true}], now, 'all').map(m => m.id), ['far','later','same-week','next'])
})
test('handles missing query data and excludes invalid times and missing tip values', () => {
  assert.deepEqual(rankUpcomingValueBets(undefined, now), [])
  assert.deepEqual(rankUpcomingValueBets([fixture('bad','invalid',4), fixture('empty','2026-10-13T19:00:00Z',0)],now), [])
})
