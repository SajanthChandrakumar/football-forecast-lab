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
    message: 'Nicht erfasst',
  })
})


test('lineupState distinguishes provider errors and one-sided lineups from unpublished data', () => {
  assert.equal(lineupState({ status: 'failed', reason: 'provider_error' }, 'Lens', 'Sporting CP').message, 'Abruf fehlgeschlagen')
  assert.equal(lineupState({ status: 'unavailable', reason: 'lineups_not_published' }, 'Lens', 'Sporting CP').message, 'Vom Anbieter noch nicht veröffentlicht')
  assert.equal(lineupState({ status: 'fresh', lineups: { Lens: { starters: [{ name: 'A' }] } } }, 'Lens', 'Sporting CP').partial, true)
})
