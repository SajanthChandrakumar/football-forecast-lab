import test from 'node:test'
import assert from 'node:assert/strict'
import { modelInputFreshness } from '../src/lib/match-freshness.mjs'

const now = Date.parse('2026-10-24T12:00:00Z')
const fresh = '2026-10-24T11:00:00Z'
const base = (overrides = {}) => ({
  source_mode: 'odds+elo',
  input_provenance: {
    odds: { observed_at: fresh },
    elo: { observed_at: fresh },
  },
  ...overrides,
})

test('requires fresh timestamps for every source used by the forecast', () => {
  assert.equal(modelInputFreshness(base(), now).status, 'fresh')
  assert.equal(modelInputFreshness(base({ input_provenance: { odds: { observed_at: fresh } } }), now).status, 'unknown')
  assert.equal(modelInputFreshness(base({ source_mode: 'odds-only', input_provenance: { odds: { observed_at: fresh } } }), now).status, 'fresh')
})

test('stale, future, and missing source times never certify fresh model inputs', () => {
  assert.equal(modelInputFreshness(base({ input_provenance: {
    odds: { observed_at: '2026-10-23T11:59:59Z' }, elo: { observed_at: fresh },
  } }), now).status, 'stale')
  assert.equal(modelInputFreshness(base({ input_provenance: {
    odds: { observed_at: '2026-10-24T12:00:01Z' }, elo: { observed_at: fresh },
  } }), now).status, 'unknown')
  assert.equal(modelInputFreshness(base({ input_provenance: {} }), now).status, 'unknown')
})
