import test from 'node:test'
import assert from 'node:assert/strict'
import {
  formatDataStatus,
  formatObservedAt,
  formatScoreFields,
  parseScoreFields,
  parseTipCountRows,
} from '../src/features/detail/detail-form.mjs'

test('parses a saved score into editable goal fields', () => {
  assert.deepEqual(parseScoreFields('2:1'), { home: '2', away: '1' })
  assert.equal(parseScoreFields('2-x'), null)
  assert.equal(parseScoreFields(null), null)
})

test('accepts only complete nonnegative integer scores for saving', () => {
  assert.equal(formatScoreFields('02', '1'), '2:1')
  assert.equal(formatScoreFields('', '1'), null)
  assert.equal(formatScoreFields('-1', '1'), null)
  assert.equal(formatScoreFields('1.5', '1'), null)
})

test('turns optional score and count rows into the pool API map', () => {
  assert.deepEqual(parseTipCountRows([
    { tip: '1:0', count: '3' },
    { tip: '1:0', count: '2' },
    { tip: '', count: '' },
    { tip: '0:0', count: '0' },
  ]), { '1:0': 5 })
  assert.deepEqual(parseTipCountRows([]), {})
  assert.equal(parseTipCountRows([{ tip: '1:', count: '2' }]), null)
  assert.equal(parseTipCountRows([{ tip: '1:0', count: '-1' }]), null)
})

test('translates data status and shows an understandable observed time age', () => {
  assert.equal(formatDataStatus('fresh'), 'Zeitpunkt nicht bestätigt')
  assert.equal(formatDataStatus('unavailable'), 'Nicht verfügbar')
  assert.equal(formatDataStatus('custom_status'), 'custom status')
  assert.match(formatObservedAt('2026-09-30T10:00:00Z', Date.parse('2026-10-02T10:00:00Z')), /^Stand .+ · vor 2 Tagen$/)
  assert.equal(formatObservedAt(undefined), 'Zeitpunkt nicht verfügbar')
})

test('an old observation is not presented as current even when the stored source says fresh', () => {
  const now = Date.parse('2026-10-02T10:00:00Z')
  assert.equal(formatDataStatus('fresh', '2026-09-24T10:00:00Z', now), 'Älterer Datenstand')
  assert.equal(formatDataStatus('fresh', '2026-10-02T09:00:00Z', now), 'Aktuell')
  assert.equal(formatDataStatus('unavailable', '2026-09-24T10:00:00Z', now), 'Nicht verfügbar')
  assert.equal(formatDataStatus('fresh', undefined, now), 'Zeitpunkt nicht bestätigt')
})
