import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')

test('match form wire type stays additive and keeps detailed cached matches', () => {
  const types = read('src/lib/types.ts')
  assert.match(types, /export interface TeamFormMatch/)
  assert.match(types, /status\?: TeamFormStatus/)
  assert.match(types, /matches\?: TeamFormMatch\[\]/)
  assert.match(types, /competition_name: string/)
  assert.match(types, /opponent_name: string/)
})

test('form badges expose result words and an explicit unavailable state', () => {
  const badges = read('src/components/shared/Badges.tsx')
  assert.match(badges, /Form nicht verfügbar/)
  assert.match(badges, /aria-label=/)
  assert.match(badges, /Sieg/)
  assert.match(badges, /Unentschieden/)
  assert.match(badges, /Niederlage/)
  assert.match(badges, /slice\(-5\)/)
})

test('compact fixture cards identify both teams and prioritise the model tip', () => {
  const row = read('src/features/dashboard/FixtureRow.tsx')
  assert.match(row, /<TeamLogo name=\{match\.home_team\}/)
  assert.match(row, /<TeamLogo name=\{match\.away_team\}/)
  assert.match(row, /Modelltipp/)
  assert.match(row, /min-h-11/)
})

test('match detail lists the five newest competitive matches in a mobile stack', () => {
  const detail = read('src/features/detail/DetailView.tsx')
  assert.match(detail, /Letzte Pflichtspiele/)
  assert.match(detail, /form\?\.matches/)
  assert.match(detail, /slice\(0, 5\)/)
  assert.match(detail, /opponent_name/)
  assert.match(detail, /competition_name/)
  assert.match(detail, /shortDate\(item\.played_at\)/)
  assert.match(detail, /sm:grid-cols-2/)
  assert.match(detail, /Form nicht verfügbar/)
  assert.match(detail, /Quelle:/)
  assert.match(detail, /ESPN \+ FotMob/)
})
