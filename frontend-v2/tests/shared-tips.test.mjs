import test from 'node:test'
import assert from 'node:assert/strict'
import { openUnsubmittedTips } from '../src/lib/shared-tips.mjs'

const now = Date.parse('2026-10-10T12:00:00Z')
const match = (id, kickoff, overrides = {}) => ({
  id,
  completed: false,
  raw_match: { commence_time: kickoff },
  ...overrides,
})
const entry = (userTip = null) => ({ prediction: { user_tip: userTip } })

test('lists only archived, upcoming matches with no saved shared tip before the T-5 cutoff', () => {
  const matches = [
    match('open', '2026-10-10T13:00:00Z'),
    match('saved', '2026-10-10T13:00:00Z'),
    match('closed', '2026-10-10T12:04:59Z'),
    match('missing-archive', '2026-10-10T14:00:00Z'),
    match('no-time', null),
    match('played', '2026-10-10T11:00:00Z'),
  ]
  const archive = {
    open: entry(),
    saved: entry('1:0'),
    closed: entry(),
    played: entry(),
  }
  assert.deepEqual(openUnsubmittedTips(matches, archive, now).map(({ id }) => id), ['open'])
})

test('accepts the exact instant five minutes before kickoff as closed', () => {
  const matches = [match('cutoff', '2026-10-10T12:05:00Z')]
  assert.deepEqual(openUnsubmittedTips(matches, { cutoff: entry() }, now), [])
})
