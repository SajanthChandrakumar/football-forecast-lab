import test from 'node:test'
import assert from 'node:assert/strict'
import {
  readTeamSelection,
  resolveInitialTeamSelection,
  sanitizeTeamSelection,
  writeTeamSelection,
} from '../src/lib/team-selection.mjs'

function storage(initial = {}) {
  const values = new Map(Object.entries(initial))
  return {
    getItem: (key) => values.has(key) ? values.get(key) : null,
    setItem: (key, value) => values.set(key, value),
  }
}

test('sanitizes comparison selections to unique nonempty names and four teams', () => {
  assert.deepEqual(sanitizeTeamSelection(['  Bayern ', 'Bayern', '', null, 'Arsenal', 'Inter', 'Roma', 'Porto']), [
    'Bayern', 'Arsenal', 'Inter', 'Roma',
  ])
})

test('keeps explicit empty selections distinct from an unset competition', () => {
  const store = storage()
  assert.equal(readTeamSelection('wc2026', store), null)
  writeTeamSelection('wc2026', [], store)
  writeTeamSelection('ucl2026', ['Man City', 'Arsenal'], store)
  assert.deepEqual(readTeamSelection('wc2026', store), [])
  assert.deepEqual(readTeamSelection('ucl2026', store), ['Man City', 'Arsenal'])
})

test('defaults to both available teams in the next valid fixture', () => {
  const rows = [{ team: 'Arsenal' }, { team: 'Bayern' }, { team: 'Inter' }]
  const matches = [
    { home_team: 'Inter', away_team: 'Unknown', raw_match: { commence_time: '2026-10-12T18:00:00Z' } },
    { home_team: 'Bayern', away_team: 'Arsenal', raw_match: { commence_time: '2026-10-14T18:00:00Z' } },
    { home_team: 'Arsenal', away_team: 'Inter', raw_match: { commence_time: '2026-10-13T18:00:00Z' } },
  ]
  assert.deepEqual(resolveInitialTeamSelection(null, matches, rows, Date.parse('2026-10-10T00:00:00Z')), ['Arsenal', 'Inter'])
})

test('does not replace a saved empty selection and falls back to the top ratings only when no valid fixture exists', () => {
  const rows = [{ team: 'Bayern' }, { team: 'Arsenal' }, { team: 'Inter' }]
  assert.deepEqual(resolveInitialTeamSelection([], [], rows), [])
  assert.deepEqual(resolveInitialTeamSelection(null, [
    { home_team: 'Unknown', away_team: 'Also unknown', raw_match: { commence_time: '2026-10-12T18:00:00Z' } },
  ], rows), ['Bayern', 'Arsenal'])
})

test('resolves fixture aliases to the comparison names shown by ratings', () => {
  const rows = [{ team: 'Manchester City' }, { team: 'Arsenal' }]
  const matches = [{ home_team: 'Man City', away_team: 'Arsenal', raw_match: { commence_time: '2026-10-12T18:00:00Z' } }]
  assert.deepEqual(resolveInitialTeamSelection(null, matches, rows, Date.parse('2026-10-10T00:00:00Z')), ['Manchester City', 'Arsenal'])
  assert.deepEqual(resolveInitialTeamSelection(['Man City', 'Arsenal'], [], rows), ['Manchester City', 'Arsenal'])
})
