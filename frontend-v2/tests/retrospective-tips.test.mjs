import test from 'node:test'
import assert from 'node:assert/strict'
import {
  applyRetrospectiveTips,
  importRetrospectiveTips,
  readRetrospectiveTips,
} from '../src/lib/retrospective-tips.mjs'

function memoryStorage() {
  const values = new Map()
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
  }
}

const archive = {
  match1: {
    metadata: { home_team: 'AEK Athens', away_team: 'LASK', commence_time: '2026-09-08T16:45:00Z', is_ko_phase: false },
    prediction: { user_tip: null },
    post_match_result: { status: 'completed', actual_score: '1:0', points_earned: null },
  },
}

test('private import matches completed fixtures, scores tips, and overlays only locally', () => {
  const storage = memoryStorage()
  const imported = importRetrospectiveTips('ucl2026', [{
    date: '2026-09-08', home_team: 'AEK Athen', away_team: 'Linzer ASK',
    tip: '2:1', actual_score: '1:0', points: 8,
  }], archive, storage)

  assert.deepEqual(imported, { imported: 1, points: 8, errors: [] })
  const saved = readRetrospectiveTips('ucl2026', storage)
  const effective = applyRetrospectiveTips(archive, saved)
  assert.equal(effective.match1.prediction.user_tip, '2:1')
  assert.equal(effective.match1.prediction.local_user_tip, true)
  assert.equal(effective.match1.post_match_result.points_earned, 8)
  assert.equal(archive.match1.prediction.user_tip, null)
})

test('private import rejects an incorrect actual score instead of attaching a tip to the wrong match', () => {
  const storage = memoryStorage()
  const imported = importRetrospectiveTips('ucl2026', [{
    date: '2026-09-08', home_team: 'AEK Athens', away_team: 'LASK',
    tip: '2:1', actual_score: '2:0', points: 8,
  }], archive, storage)

  assert.equal(imported.imported, 0)
  assert.equal(imported.points, 0)
  assert.equal(imported.errors.length, 1)
  assert.equal(Object.keys(readRetrospectiveTips('ucl2026', storage)).length, 0)
})

test('private point calculation follows the SRF goal, tendency, and knockout scoring', () => {
  const storage = memoryStorage()
  const knockoutArchive = {
    ...archive,
    match1: { ...archive.match1, metadata: { ...archive.match1.metadata, is_ko_phase: true } },
  }
  const imported = importRetrospectiveTips('ucl2026', [{
    date: '2026-09-08', home_team: 'AEK Athens', away_team: 'LASK',
    tip: '2:1', actual_score: '1:0', points: 16,
  }], knockoutArchive, storage)

  assert.deepEqual(imported, { imported: 1, points: 16, errors: [] })
})
