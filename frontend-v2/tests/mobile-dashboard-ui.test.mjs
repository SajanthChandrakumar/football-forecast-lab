import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')

// Navigation, dialog focus and Escape are exercised against the browser in e2e/navigation.spec.ts.

test('dashboard uses plain-language mobile prediction cards', () => {
  const row = read('src/features/dashboard/FixtureRow.tsx')
  assert.match(row, /Modelltipp/)
  assert.match(row, /min-h-11/)
  assert.match(row, /trailing != null/)
})

// Source-aware chances and preserved detail context are verified in e2e/data-status and matchcenter specs.

test('detail exposes local copy first and discloses that the saved tip is shared', () => {
  const detail = read('src/features/detail/DetailView.tsx')
  const tipEditor = read('src/components/shared/SharedTipEditor.tsx')
  assert.match(detail, /Tipp kopieren/)
  assert.match(detail, /<SharedTipEditor/)
  assert.match(tipEditor, /formatScoreFields/)
  assert.match(tipEditor, /sharedTipIsOpen/)
  assert.match(tipEditor, /targetCompetition: competition/)
  assert.match(detail, /nicht nutzergetrennt/)
  assert.match(detail, /navigator\.clipboard\.writeText/)
})

test('score table uses team names when display names are missing', () => {
  const detail = read('src/features/detail/DetailView.tsx')
  assert.match(detail, /homeDisp=\{match\.home_disp \|\| match\.home_team\}/)
  assert.match(detail, /awayDisp=\{match\.away_disp \|\| match\.away_team\}/)
})

test('past fixtures without a result are separated and no longer offer a tip', () => {
  const dashboard = read('src/features/dashboard/DashboardView.tsx')
  const row = read('src/features/dashboard/FixtureRow.tsx')
  assert.match(dashboard, /pendingResult/)
  assert.match(dashboard, /Ergebnis ausstehend/)
  assert.match(dashboard, /Anstoß offen/)
  assert.match(row, /pendingResult/)
  assert.match(row, /Ergebnis ausstehend/)
})

test('unavailable match data keeps its status and last observation for the empty state', () => {
  const queries = read('src/hooks/queries.ts')
  const dashboard = read('src/features/dashboard/DashboardView.tsx')
  assert.match(queries, /observed_at/)
  assert.match(dashboard, /Spieldaten gerade nicht verfügbar/)
  assert.match(dashboard, /observed_at/)
})

test('built index references assets that exist in the release artifact', () => {
  const index = read('dist/index.html')
  const assets = [...index.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map(([, path]) => path)
  assert.ok(assets.length >= 2)
  for (const path of assets) assert.ok(existsSync(new URL(`../dist${path}`, import.meta.url)), path)
})
