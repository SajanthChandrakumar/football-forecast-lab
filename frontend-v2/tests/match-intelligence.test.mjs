import test from 'node:test'
import assert from 'node:assert/strict'

import { lineupState } from '../src/lib/match-intelligence.mjs'


test('lineupState exposes confirmed lineups without hiding substitutes', () => {
  const state = lineupState({
    status: 'fresh',
    source: 'espn',
    observed_at: '2026-10-13T18:30:00+00:00',
    lineups: {
      Lens: { starters: [{ name: 'A' }], substitutes: [{ name: 'B' }] },
      'Sporting CP': { starters: [{ name: 'C' }], substitutes: [] },
    },
  }, 'Lens', 'Sporting CP')

  assert.equal(state.kind, 'confirmed')
  assert.equal(state.home.starters[0].name, 'A')
  assert.equal(state.home.substitutes[0].name, 'B')
})


test('lineupState distinguishes not-yet-collected data', () => {
  assert.deepEqual(lineupState(undefined, 'Lens', 'Sporting CP'), {
    kind: 'unavailable',
    message: 'Aufstellungen sind noch nicht veröffentlicht.',
  })
})
