import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')

test('mobile shell exposes the approved three-item navigation', () => {
  const shell = read('src/components/layout/AppShell.tsx')
  assert.match(shell, /Spiele/)
  assert.match(shell, /Meine Tipps/)
  assert.match(shell, /Mehr/)
  assert.match(shell, /to: '\/'/)
  assert.match(shell, /to: '\/performance'/)
  assert.match(shell, /lg:hidden/)

  const mehrTriggers = shell.match(/<button[\s\S]*?(?:aria-expanded=\{moreOpen\}|aria-label="Mehr öffnen")[\s\S]*?Mehr[\s\S]*?<\/button>/g) ?? []
  assert.equal(mehrTriggers.length, 1, 'the shell must expose one mobile Mehr trigger')
})

test('mobile Mehr menu has dialog, focus, Escape, and close contracts', () => {
  const shell = read('src/components/layout/AppShell.tsx')
  assert.match(shell, /aria-controls="mobile-more-menu"/)
  assert.match(shell, /id="mobile-more-menu"/)
  assert.match(shell, /role="dialog"/)
  assert.match(shell, /aria-modal="true"/)
  assert.match(shell, /useRef/)
  assert.match(shell, /\.focus\(\)/)
  assert.match(shell, /event\.key [!=]+ 'Escape'/)
  assert.match(shell, /onClick=\{onNavigate\}/)
})

test('dashboard uses plain-language mobile prediction cards', () => {
  const row = read('src/features/dashboard/FixtureRow.tsx')
  assert.match(row, /Modelltipp/)
  assert.match(row, /min-h-11/)
  assert.match(row, /\{trailing\}/)
})

test('dashboard and detail share the automatic hint component', () => {
  const card = read('src/components/shared/MatchHintCard.tsx')
  const dashboard = read('src/features/dashboard/FixtureRow.tsx')
  const detail = read('src/features/detail/DetailView.tsx')

  assert.match(card, /buildMatchHint/)
  assert.match(card, /Sicherheit/)
  assert.match(card, /<details/)
  assert.match(card, /Warum\?/)
  assert.match(card, /min-h-11/)
  assert.match(card, /compact \? 'text-sm' : 'text-base'/)
  assert.match(dashboard, /<MatchHintCard match=\{match\}/)
  assert.match(detail, /<MatchHintCard match=\{match\}/)
})

test('fixture cards show the model tip, a short reason and an explicit detail action', () => {
  const row = read('src/features/dashboard/FixtureRow.tsx')
  assert.match(row, /Modelltipp/)
  assert.match(row, /<MatchHintCard match=\{match\} compact/)
  assert.match(row, /Tipp ansehen/)
})

test('detail exposes local copy first and discloses that the saved tip is shared', () => {
  const detail = read('src/features/detail/DetailView.tsx')
  assert.match(detail, /Tipp kopieren/)
  assert.match(detail, /Gemeinsamen Spieltipp speichern/)
  assert.match(detail, /nicht nutzergetrennt/)
  assert.match(detail, /navigator\.clipboard\.writeText/)
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

test('global styling uses the approved palette and removes the blueprint grid', () => {
  const css = read('src/index.css')
  assert.match(css, /#315efb/i)
  assert.match(css, /#edf1f6/i)
  assert.doesNotMatch(css, /blueprint grid/i)
})

test('built index references assets that exist in the release artifact', () => {
  const index = read('dist/index.html')
  const assets = [...index.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map(([, path]) => path)
  assert.ok(assets.length >= 2)
  for (const path of assets) assert.ok(existsSync(new URL(`../dist${path}`, import.meta.url)), path)
})
