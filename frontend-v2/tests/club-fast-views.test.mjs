import test from 'node:test'
import assert from 'node:assert/strict'
import { api } from '../src/lib/api.ts'

test('reads core, analysis, and archive through selected-game endpoints', async () => {
  assert.equal(typeof api.matchCore, 'function')
  assert.equal(typeof api.matchAnalysis, 'function')

  const originalFetch = globalThis.fetch
  const paths = []
  const responses = [
    { status: 'processing', data: [], source: 'club_views', reason: 'preparing', retry_after: 2 },
    { id: 'ucl-next', view_version: 'read-v1' },
    { uclNext: { prediction: { user_tip: null } } },
  ]
  globalThis.fetch = async url => {
    paths.push(new URL(url, 'http://localhost'))
    return new Response(JSON.stringify(responses.shift()), { status: paths.length === 1 ? 202 : 200, headers: { 'Content-Type': 'application/json' } })
  }
  try {
    const processing = await api.matchCore('ucl2026', 'ucl-next')
    await api.matchAnalysis('ucl2026', 'ucl-next')
    await api.archive('ucl2026', 'ucl-next')

    assert.equal(processing.status, 'processing')
    assert.deepEqual(paths.map(url => url.pathname), [
      '/api/matches/ucl-next',
      '/api/matches/ucl-next/analysis',
      '/api/archive',
    ])
    assert.deepEqual(paths.map(url => url.searchParams.get('competition')), ['ucl2026', 'ucl2026', 'ucl2026'])
    assert.equal(paths[2].searchParams.get('match_id'), 'ucl-next')
  } finally {
    globalThis.fetch = originalFetch
  }
})
