import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')

test('match form wire type stays additive and keeps detailed cached matches', () => {
  const types = read('src/lib/types.ts')
  assert.match(types, /export interface TeamFormMatch/)
  assert.match(types, /scope\?: 'league'/)
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

test('match detail lists the ten newest competitive matches in a mobile stack', () => {
  const detail = read('src/features/detail/DetailView.tsx')
  assert.match(detail, /Letzte Pflichtspiele/)
  assert.match(detail, /form\?\.matches/)
  assert.match(detail, /slice\(0, 10\)/)
  assert.match(detail, /opponent_name/)
  assert.match(detail, /competition_name/)
  assert.match(detail, /shortDate\(item\.played_at\)/)
  assert.match(detail, /lg:grid-cols-2/)
  assert.match(detail, /Form nicht verfügbar/)
  assert.match(detail, /Quelle:/)
  assert.match(detail, /ESPN \+ FotMob/)
  assert.match(detail, /Die Form beschreibt separat zuletzt erfasste Premier-League-Spiele, keine anderen Wettbewerbe/)
})

test('league-scoped history states its Premier League scope and reads the shared lineup archive', () => {
  const detail = read('src/features/detail/DetailView.tsx')
  assert.match(detail, /form\?\.scope === 'league'/)
  assert.match(detail, /nur zuletzt erfasste Premier-League-Spiele, keine anderen Wettbewerbe/)
  assert.match(detail, /<HistoricalMatchRow key=\{item.fixture_id\} item=\{item\} \/>/)
  assert.match(detail, /useMatchHistory\(item.fixture_id, open\)/)
})

test('Premier League detail does not promise unsupported player or lineup updates', () => {
  const detail = read('src/features/detail/DetailView.tsx')
  assert.match(detail, /const isPremierLeague = competition === 'epl2026'/)
  assert.match(detail, /Diese Seite liest nur gespeicherte Daten/)
  assert.match(detail, /isPremierLeague \? 'Premier League'/)
  assert.match(detail, /Ligaspiele werden schrittweise archiviert/)
  assert.match(detail, /lineup.formation/)
})
