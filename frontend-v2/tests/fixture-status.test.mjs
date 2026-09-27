import test from 'node:test'
import assert from 'node:assert/strict'
import { fixtureStatus, preferredFixtureTab, sharedTipIsOpen } from '../src/lib/fixture-status.mjs'

const matchAt = (commence_time, extra = {}) => ({
  raw_match: { commence_time },
  ...extra,
})

test('classifies future, overdue and completed fixtures against the supplied clock', () => {
  const now = Date.parse('2026-09-27T12:00:00Z')
  assert.equal(fixtureStatus(matchAt('2026-09-27T12:01:00Z'), now), 'upcoming')
  assert.equal(fixtureStatus(matchAt('2026-09-27T12:00:00Z'), now), 'pending')
  assert.equal(fixtureStatus(matchAt('2026-09-27T11:59:00Z'), now), 'pending')
  assert.equal(fixtureStatus(matchAt('2026-09-27T11:59:00Z', { actual_score: '2:1' }), now), 'played')
  assert.equal(fixtureStatus(matchAt('invalid'), now), 'unscheduled')
  assert.equal(fixtureStatus(matchAt(undefined), now), 'unscheduled')
})

test('opens completed games when a competition has no upcoming games', () => {
  assert.equal(preferredFixtureTab({ upcoming: 0, pending: 0, played: 99, unscheduled: 0 }), 'played')
  assert.equal(preferredFixtureTab({ upcoming: 0, pending: 7, played: 99, unscheduled: 0 }), 'played')
})

test('shared tips close five minutes before kickoff', () => {
  const kickoff = '2026-09-27T12:05:00Z'
  assert.equal(sharedTipIsOpen(kickoff, Date.parse('2026-09-27T11:59:59Z')), true)
  assert.equal(sharedTipIsOpen(kickoff, Date.parse('2026-09-27T12:00:00Z')), false)
  assert.equal(sharedTipIsOpen('invalid'), false)
})
