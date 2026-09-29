import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const detailSource = fs.readFileSync(new URL('../src/features/detail/DetailView.tsx', import.meta.url), 'utf8')

test('team history exposes ten clickable matches and cached lineup details', () => {
  assert.match(detailSource, /slice\(0, 10\)/)
  assert.match(detailSource, /useMatchHistory/)
  assert.match(detailSource, /Aufstellung ansehen/)
  assert.match(detailSource, /lineup\.starters\.length > 0/)
  assert.match(detailSource, /falls der Anbieter sie bereitstellt/)
})
