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

test('private import matches the team names used by the live archive', () => {
  const storage = memoryStorage()
  const liveNamesArchive = {
    aek: {
      metadata: { home_team: 'AEK Athens', away_team: 'LASK Linz', commence_time: '2026-09-08T16:45:00Z', is_ko_phase: false },
      prediction: {},
      post_match_result: { status: 'completed', actual_score: '1:0' },
    },
    madrid: {
      metadata: { home_team: 'Real Madrid', away_team: 'Internazionale', commence_time: '2026-09-08T19:00:00Z', is_ko_phase: false },
      prediction: {},
      post_match_result: { status: 'completed', actual_score: '2:1' },
    },
    bayern: {
      metadata: { home_team: 'Bayern Munich', away_team: 'Bodo/Glimt', commence_time: '2026-09-10T19:00:00Z', is_ko_phase: false },
      prediction: {},
      post_match_result: { status: 'completed', actual_score: '5:0' },
    },
  }
  const imported = importRetrospectiveTips('ucl2026', [
    { date: '2026-09-08', home_team: 'AEK Athen', away_team: 'Linzer ASK', tip: '2:1', actual_score: '1:0', points: 8 },
    { date: '2026-09-08', home_team: 'Real Madrid', away_team: 'Inter Mailand', tip: '2:1', actual_score: '2:1', points: 10 },
    { date: '2026-09-10', home_team: 'FC Bayern München', away_team: 'FK Bodø/Glimt', tip: '4:1', actual_score: '5:0', points: 5 },
  ], liveNamesArchive, storage)

  assert.deepEqual(imported, { imported: 3, points: 23, errors: [] })
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
