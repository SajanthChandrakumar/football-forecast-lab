import test from 'node:test'
import assert from 'node:assert/strict'
import { getSavedTipForMatch, openUnsubmittedTips } from '../src/lib/shared-tips.mjs'
import { buildAssistantRows } from '../src/lib/matchday-assistant.mjs'

const now = Date.parse('2026-10-03T12:00:00Z')
const fixture = (id, extra = {}) => ({
  id,
  home_team: 'Arsenal',
  away_team: 'Chelsea',
  top_tip: '2:1',
  source_mode: 'odds-only',
  status: 'fresh',
  observed_at: new Date(now).toISOString(),
  raw_match: { id, commence_time: new Date(now + 86_400_000).toISOString() },
  ...extra,
})
const entry = user_tip => ({ prediction: { user_tip } })

test('a cached prepared tip covers a missing canonical archive row', () => {
  const match = fixture('canonical-1', { user_tip: '3:1' })
  assert.equal(getSavedTipForMatch(match, {}), '3:1')
  assert.deepEqual(openUnsubmittedTips([match], {}, now), [])
  assert.equal(buildAssistantRows([match], {}, {}, {}, now, 'epl2026')[0].savedTip, '3:1')
})

test('an archive_id alias wins over a stale duplicate canonical row', () => {
  const match = fixture('canonical-2', { archive_id: 'legacy-row', user_tip: null })
  const archive = { 'legacy-row': entry('4:2'), 'canonical-2': entry(null) }
  assert.equal(getSavedTipForMatch(match, archive), '4:2')
  assert.deepEqual(openUnsubmittedTips([match], archive, now), [])
  assert.equal(buildAssistantRows([match], archive, {}, {}, now, 'epl2026')[0].savedTip, '4:2')
})

test('a cached prepared tip survives an explicit null canonical archive row', () => {
  const match = fixture('canonical-3', { user_tip: '1:0' })
  const archive = { 'canonical-3': entry(null) }
  assert.equal(getSavedTipForMatch(match, archive), '1:0')
  assert.deepEqual(openUnsubmittedTips([match], archive, now), [])
  assert.equal(buildAssistantRows([match], archive, {}, {}, now, 'epl2026')[0].savedTip, '1:0')
})

test('an explicit null archive tip with no prepared tip remains open', () => {
  const match = fixture('canonical-4', { user_tip: null })
  const archive = { 'canonical-4': entry(null) }
  assert.equal(getSavedTipForMatch(match, archive), '')
  assert.deepEqual(openUnsubmittedTips([match], archive, now).map(({ id }) => id), ['canonical-4'])
})
