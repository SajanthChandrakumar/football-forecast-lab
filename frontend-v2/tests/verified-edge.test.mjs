import test from 'node:test'
import assert from 'node:assert/strict'
import { hasVerifiedPreMatchEdge } from '../src/lib/verified-edge.mjs'

test('a cached historical edge alone is not a verified pre-match sample', () => {
  assert.equal(hasVerifiedPreMatchEdge({ edge_home: 0.17, actual_score: '2:1', raw_match: { commence_time: '2026-10-01T12:00:00Z' } }), false)
})

test('a frozen model forecast with both source times before kickoff qualifies', () => {
  assert.equal(hasVerifiedPreMatchEdge({
    raw_match: { commence_time: '2026-10-01T12:00:00Z' },
    evaluation_forecast: {
      frozen_at: '2026-10-01T11:50:00Z', model_version: 'club-v2',
      probabilities: { model: { home: 0.5, draw: 0.3, away: 0.2 } },
      input_provenance: {
        odds: { observed_at: '2026-10-01T11:40:00Z' },
        elo: { observed_at: '2026-10-01T11:40:00Z' },
      },
    },
  }), true)
})
