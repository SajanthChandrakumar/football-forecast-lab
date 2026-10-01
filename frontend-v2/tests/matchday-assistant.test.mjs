import test from 'node:test'
import assert from 'node:assert/strict'
import {
  buildAssistantRows,
  getSaveCandidates,
  isValidScoreTip,
  saveTipBatch,
} from '../src/lib/matchday-assistant.mjs'

const futureKickoff = '2026-10-01T18:00:00Z'
const match = (id, overrides = {}) => ({
  id,
  home_team: `Home ${id}`,
  away_team: `Away ${id}`,
  top_tip: '2:1',
  completed: false,
  raw_match: { commence_time: futureKickoff },
  ...overrides,
})

test('uses a saved tip over the model suggestion and closes editing at T-5', () => {
  const savedMatch = match('saved')
  savedMatch.raw_match.commence_time = '2026-10-01T18:06:00Z'
  const rows = buildAssistantRows(
    [savedMatch, match('locked', { raw_match: { commence_time: '2026-10-01T18:05:00Z' } })],
    { saved: { prediction: { user_tip: '0:0' } } },
    {},
    {},
    Date.parse('2026-10-01T18:00:00Z'),
  )

  assert.equal(rows[0].value, '0:0')
  assert.equal(rows[0].savedTip, '0:0')
  assert.equal(rows[0].editable, true)
  assert.equal(rows[1].editable, false)
})

test('never offers completed fixtures and accepts only backend-bounded scores', () => {
  const [row] = buildAssistantRows(
    [match('done', { completed: true })],
    {}, {}, {}, Date.parse('2026-09-30T12:00:00Z'),
  )
  assert.equal(row.editable, false)
  assert.equal(row.value, '')
  assert.equal(isValidScoreTip('0:20'), true)
  assert.equal(isValidScoreTip('21:0'), false)
  assert.equal(isValidScoreTip('2:1x'), false)
})

test('labels forecast sources in German, marks stale data, and does not prefill unavailable tips', () => {
  const rows = buildAssistantRows([
    match('combined', { source_mode: 'odds+elo', status: 'stale', observed_at: '2026-09-30T12:00:00Z' }),
    match('elo', { source_mode: 'elo-only', status: 'fresh' }),
    match('quote', { source_mode: 'odds-only', status: 'fresh' }),
    match('unavailable', { source_mode: 'unavailable', status: 'unavailable', top_tip: '3:0' }),
    match('failed', { source_mode: 'odds+elo', status: 'unavailable', source_status: 'stale' }),
  ], {}, {}, {}, Date.parse('2026-09-30T12:00:00Z'))

  assert.deepEqual(rows.map(({ sourceLabel, stale, observedAt, suggestion, value }) => [sourceLabel, stale, observedAt, suggestion, value]), [
    ['Buchmacher + Elo', true, '2026-09-30T12:00:00Z', '2:1', '2:1'],
    ['Elo', false, '', '2:1', '2:1'],
    ['Quote', false, '', '2:1', '2:1'],
    ['Keine Prognose verfügbar', false, '', '', ''],
    ['Buchmacher + Elo', true, '', '', ''],
  ])
})

test('saves only changed, valid, currently editable tips', () => {
  const rows = buildAssistantRows(
    [match('suggestion'), match('saved'), match('invalid')],
    { saved: { prediction: { user_tip: '2:1' } } },
    { suggestion: '3:0', saved: '4:1', invalid: '21:0' },
    {},
    Date.parse('2026-09-30T12:00:00Z'),
  )

  assert.deepEqual(getSaveCandidates(rows).map(({ match: item, tip }) => [item.id, tip]), [
    ['suggestion', '3:0'],
    ['saved', '4:1'],
  ])
})

test('limits one save action to 18 tips, runs at most three requests, and reports partial failure', async () => {
  const items = Array.from({ length: 20 }, (_, index) => ({ id: String(index) }))
  let active = 0
  let peak = 0
  const attempts = []
  const { results, remaining } = await saveTipBatch(items, async (item) => {
    attempts.push(item.id)
    active += 1
    peak = Math.max(peak, active)
    await new Promise((resolve) => setTimeout(resolve, 2))
    active -= 1
    if (item.id === '4') throw new Error('409 T-5')
  })

  assert.equal(peak, 3)
  assert.equal(attempts.length, 18)
  assert.equal(remaining, 2)
  assert.equal(results.filter((result) => !result.ok).length, 1)
  assert.equal(attempts.filter((id) => id === '4').length, 1)
})
