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
