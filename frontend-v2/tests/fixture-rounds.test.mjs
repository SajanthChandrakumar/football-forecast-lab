import test from 'node:test'
import assert from 'node:assert/strict'
import { groupFixturesByRound } from '../src/lib/fixture-rounds.mjs'

const match = (id, commence_time, round = 'league stage') => ({
  id,
  raw_match: { commence_time, round },
})

test('groups UCL fixtures into dated Spielwochen using the full schedule', () => {
  const rounds = groupFixturesByRound([
    match('3', '2026-10-14T19:00:00Z'),
    match('1', '2026-09-22T19:00:00Z'),
    match('2', '2026-10-13T16:45:00Z'),
  ])
  assert.deepEqual(rounds.map((round) => [round.label, round.matches.map((item) => item.id)]), [
    ['Spielwoche 1', ['1']],
    ['Spielwoche 2', ['2', '3']],
  ])
})

test('keeps broad league round labels on the existing date-based Spielwochen', () => {
  const rounds = groupFixturesByRound([
    match('late', '2026-10-12T19:00:00Z', 'Regular Season'),
    match('early', '2026-10-04T14:00:00Z', 'Regular Season'),
  ])
  assert.deepEqual(rounds.map((round) => [round.label, round.matches.map((item) => item.id)]), [
    ['Spielwoche 1', ['early']],
    ['Spielwoche 2', ['late']],
  ])
})

test('keeps a named knockout round together and puts undated games in their own group', () => {
  const rounds = groupFixturesByRound([
    match('3', undefined),
    match('1', '2026-11-03T19:00:00Z', 'round of 16'),
    match('2', '2026-11-10T19:00:00Z', 'round of 16'),
  ])
  assert.deepEqual(rounds.map((round) => [round.label, round.matches.map((item) => item.id)]), [
    ['Achtelfinale', ['1', '2']],
    ['Anstoß offen', ['3']],
  ])
})

test('groups days in Zurich time, labels today and tomorrow, and sorts kickoff times', async () => {
  const { groupFixturesByDay } = await import('../src/lib/fixture-rounds.mjs')
  assert.equal(typeof groupFixturesByDay, 'function')
  const groups = groupFixturesByDay([
    match('late', '2026-10-20T19:00:00Z'),
    match('tomorrow', '2026-10-20T22:30:00Z'),
    match('early', '2026-10-20T16:45:00Z'),
    match('unknown', undefined),
  ], Date.parse('2026-10-20T12:00:00Z'))
  assert.deepEqual(groups.map(day => [day.key, day.relativeLabel, day.matches.map(m => m.id)]), [
    ['2026-10-20', 'Heute', ['early', 'late']],
    ['2026-10-21', 'Morgen', ['tomorrow']],
    ['undated', null, ['unknown']],
  ])
})

test('tomorrow remains the next Zurich calendar day across the autumn clock change', async () => {
  const { groupFixturesByDay } = await import('../src/lib/fixture-rounds.mjs')
  assert.equal(typeof groupFixturesByDay, 'function')
  const groups = groupFixturesByDay([match('next', '2026-10-25T23:30:00Z')], Date.parse('2026-10-24T22:30:00Z'))
  assert.equal(groups[0].relativeLabel, 'Morgen')
  assert.equal(groups[0].key, '2026-10-26')
})
