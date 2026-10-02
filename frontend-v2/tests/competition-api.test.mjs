import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { COMPETITIONS, FALLBACK_COMPETITIONS, competitionPath, validCompetition } from '../src/lib/competition.mjs'
import { botFormState } from '../src/lib/customBot.mjs'
import { validPremierLeagueStandingsRows, validUclStandingsRows } from '../src/lib/standings.mjs'
import { hasScoreMatrix } from '../src/lib/prediction.mjs'
import { hasUclSimulationResults } from '../src/lib/simulation.mjs'
import * as simulation from '../src/lib/simulation.mjs'

let officialPerformance
let performanceEntryKind
let competitionLabel
let rankUpcomingValueBets
let teamFormTeamNames
let teamFormEntries
let teamFormCoverage
let teamFormSnapshotState
let teamFormCanonicalName
let teamsWithoutHistory
try {
  ({ officialPerformance, performanceEntryKind } = await import('../src/lib/performance.mjs'))
} catch {
  // The assertion below reports the missing implementation as a failed behavior test.
}
try {
  ({ competitionLabel } = await import('../src/lib/competition.mjs'))
} catch {
  // The assertion below reports the missing implementation as a failed behavior test.
}
try {
  ({ rankUpcomingValueBets } = await import('../src/lib/value-bets.mjs'))
} catch {
  // The assertion below reports the missing implementation as a failed behavior test.
}
try {
  ({ teamFormTeamNames, teamFormEntries, teamFormCoverage, teamFormSnapshotState, teamFormCanonicalName, teamsWithoutHistory } = await import('../src/lib/team-form.mjs'))
} catch {
  // The assertion below reports the missing implementation as a failed behavior test.
}

test('competitionPath URL-encodes the active competition', () => {
  assert.equal(competitionPath('/matches?force=true', 'ucl2026'), '/matches?force=true&competition=ucl2026')
})

test('validCompetition defaults invalid storage values to UCL', () => {
  assert.equal(validCompetition('wc2026'), 'wc2026')
  assert.equal(validCompetition('epl2026'), 'epl2026')
  assert.equal(validCompetition('invalid'), 'ucl2026')
  assert.equal(validCompetition(null), 'ucl2026')
})

test('fallback competition registry includes Premier League in both selectors', () => {
  assert.deepEqual(COMPETITIONS, ['wc2026', 'ucl2026', 'epl2026'])
  assert.deepEqual(FALLBACK_COMPETITIONS.find(({ id }) => id === 'epl2026'), {
    id: 'epl2026', short_name: 'PL 2026/27', display_name: 'Premier League 2026/27',
  })
  for (const path of ['../src/components/layout/Sidebar.tsx', '../src/components/layout/AppShell.tsx']) {
    assert.match(readFileSync(new URL(path, import.meta.url), 'utf8'), /FALLBACK_COMPETITIONS/)
  }
})

test('competition labels use new event metadata without presenting it as the World Cup', () => {
  assert.equal(competitionLabel('copa2030', [{ id: 'copa2030', short_name: 'Copa 2030' }]), 'Copa 2030')
  assert.equal(competitionLabel('copa2030'), 'copa2030')
})

test('a competition registered by the API can be selected', () => {
  assert.equal(validCompetition('copa2030', ['wc2026', 'ucl2026', 'copa2030']), 'copa2030')
  assert.equal(validCompetition('unregistered', ['wc2026', 'ucl2026', 'copa2030']), 'ucl2026')
})

test('botFormState reloads saved values or clean defaults', () => {
  assert.deepEqual(botFormState(undefined), {
    name: 'Mein Bot',
    params: { market_weight: 0.7, risk: 0, draw_bias: 0, underdog_bias: 0 },
  })
  assert.deepEqual(botFormState({ exists: true, name: 'UCL Bot', params: { market_weight: 0.2 } }), {
    name: 'UCL Bot',
    params: { market_weight: 0.2, risk: 0, draw_bias: 0, underdog_bias: 0 },
  })
})

test('validUclStandingsRows rejects partial, duplicate, or unranked tables', () => {
  const rows = Array.from({ length: 36 }, (_, index) => ({ team: `Team ${index}`, pos: index + 1 }))
  assert.equal(validUclStandingsRows(rows)?.length, 36)
  assert.equal(validUclStandingsRows(rows.slice(0, 35)), null)
  assert.equal(validUclStandingsRows(rows.map((row, index) => index === 35 ? { ...row, team: 'Team 0' } : row)), null)
  assert.equal(validUclStandingsRows(rows.map((row, index) => index === 35 ? { ...row, team: ' Team 0 ' } : row)), null)
  assert.equal(validUclStandingsRows(rows.map(({ team }) => ({ team }))), null)
})

test('Premier League standings require the complete, uniquely ranked 20-club table', () => {
  assert.equal(typeof validPremierLeagueStandingsRows, 'function')
  const rows = Array.from({ length: 20 }, (_, index) => ({ team: `Club ${index + 1}`, pos: index + 1 }))
  assert.equal(validPremierLeagueStandingsRows(rows)?.length, 20)
  assert.equal(validPremierLeagueStandingsRows(rows.slice(0, 19)), null)
  assert.equal(validPremierLeagueStandingsRows(rows.map((row, index) => index === 19 ? { ...row, team: 'Club 1' } : row)), null)
  assert.equal(validPremierLeagueStandingsRows(rows.map((row, index) => index === 19 ? { ...row, pos: 19 } : row)), null)

  const view = readFileSync(new URL('../src/features/groups/GroupsView.tsx', import.meta.url), 'utf8')
  assert.match(view, /competition === 'epl2026'/)
  assert.match(view, /PremierLeagueStandings/)
  const tableStart = view.indexOf('function PremierLeagueStandings')
  const tableEnd = view.indexOf('function UclStandings', tableStart)
  assert.notEqual(tableStart, -1)
  assert.notEqual(tableEnd, -1)
  const table = view.slice(tableStart, tableEnd)
  assert.doesNotMatch(table, /Top 8|qualifiz|pos <= 8|pos > 24/)
})

test('hasScoreMatrix rejects empty matrices', () => {
  assert.equal(hasScoreMatrix({}), false)
  assert.equal(hasScoreMatrix({ 0: { 0: 0, 1: 0 }, 1: { 0: 0 } }), false)
  assert.equal(hasScoreMatrix({ 0: { 0: 0.25 } }), true)
})

test('hasUclSimulationResults rejects unavailable and malformed payloads', () => {
  assert.equal(hasUclSimulationResults(undefined), false)
  assert.equal(hasUclSimulationResults({ status: 'unavailable' }), false)
  assert.equal(hasUclSimulationResults({ status: 'fresh' }), false)
  assert.equal(hasUclSimulationResults({ status: 'fresh', results: [] }), true)
})

test('UCL simulation API path defaults to 100 runs and respects an explicit count', () => {
  assert.equal(typeof simulation.uclSimulationPath, 'function')
  assert.equal(simulation.uclSimulationPath(), '/simulate_ucl?runs=100')
  assert.equal(simulation.uclSimulationPath(500), '/simulate_ucl?runs=500')
})

test('competition labels follow the active competition and its configured short name', () => {
  assert.equal(typeof competitionLabel, 'function')
  assert.equal(competitionLabel('ucl2026'), 'UCL 2026/27')
  assert.equal(competitionLabel('wc2026'), 'WM 2026')
  assert.equal(competitionLabel('ucl2026', [{ id: 'ucl2026', short_name: 'Champions League' }]), 'Champions League')
})

test('value bets include only upcoming unplayed fixtures with positive expected points', () => {
  assert.equal(typeof rankUpcomingValueBets, 'function')
  const now = Date.parse('2026-09-23T18:00:00Z')
  const futureKickoff = { raw_match: { commence_time: '2026-09-24T18:00:00Z' } }
  const ranked = rankUpcomingValueBets([
    { ...futureKickoff, id: 'upcoming-low', max_xp: 2, completed: false },
    { ...futureKickoff, id: 'played-flag', max_xp: 9, completed: true },
    { ...futureKickoff, id: 'played-score', max_xp: 8, actual_score: '2:1' },
    { ...futureKickoff, id: 'no-value', max_xp: 0 },
    { ...futureKickoff, id: 'upcoming-high', max_xp: 4, actual_score: null },
  ], now)
  assert.deepEqual(ranked.map(({ id }) => id), ['upcoming-high', 'upcoming-low'])
})

test('value bets exclude past and live kickoffs even when the result is missing', () => {
  const now = Date.parse('2026-09-23T18:00:00Z')
  const ranked = rankUpcomingValueBets([
    { id: 'past-no-result', max_xp: 9, raw_match: { commence_time: '2026-09-23T17:59:00Z' } },
    { id: 'live-no-result', max_xp: 8, raw_match: { commence_time: '2026-09-23T18:00:00Z' } },
    { id: 'future', max_xp: 4, raw_match: { commence_time: '2026-09-23T18:01:00Z' } },
  ], now)

  assert.deepEqual(ranked.map(({ id }) => id), ['future'])
})

test('value bets drop a fixture as soon as its kickoff time is reached', () => {
  const kickoff = Date.parse('2026-09-24T18:00:00Z')
  const matches = [{
    id: 'starting-now',
    max_xp: 4,
    raw_match: { commence_time: new Date(kickoff).toISOString() },
  }]

  assert.deepEqual(rankUpcomingValueBets(matches, kickoff - 1).map(({ id }) => id), ['starting-now'])
  assert.deepEqual(rankUpcomingValueBets(matches, kickoff), [])
})

test('UCL team form uses only valid standings teams and reports teams without rating history', () => {
  assert.equal(typeof teamFormTeamNames, 'function')
  assert.equal(typeof teamsWithoutHistory, 'function')
  const standings = Array.from({ length: 36 }, (_, index) => ({ team: `Club ${index + 1}`, pos: index + 1 }))
  assert.deepEqual(teamFormTeamNames('ucl2026', ['Club 1', 'Club 2', 'National Team'], standings), [])
  assert.deepEqual(teamFormTeamNames('ucl2026', ['Club 1'], standings.slice(0, 35)), [])
  assert.deepEqual(teamFormTeamNames('wc2026', ['Club 1', 'National Team'], []), ['Club 1', 'National Team'])
  assert.deepEqual(
    teamsWithoutHistory(['Club 1', 'Club 2'], { 'Club 1': [{ timestamp: 12, match_id: 'm1', elo: 2030 }] }),
    ['Club 2'],
  )
})

test('UCL team form resolves every standings display name to an existing canonical Elo key', () => {
  assert.equal(typeof teamFormEntries, 'function')
  const rows = [
    'Paris Saint-Germain', 'Bayern Munich', 'Barcelona', 'Manchester United', 'Como', 'Sporting CP',
    'VfB Stuttgart', 'Manchester City', 'Real Betis', 'Lens', 'Aston Villa', 'Borussia Dortmund',
    'Real Madrid', 'Liverpool', 'Arsenal', 'AEK Athens', 'AS Roma', 'Shakhtar Donetsk', 'Fenerbahce',
    'PSV Eindhoven', 'Villarreal', 'Slavia Prague', 'Club Brugge', 'Lille', 'Atlético Madrid',
    'Internazionale', 'LASK Linz', 'Napoli', 'Galatasaray', 'Viking FK', 'FC Porto', 'RB Leipzig',
    'Feyenoord Rotterdam', 'Sabah FK', 'Slovan Bratislava', 'Bodo/Glimt',
  ].map((team, index) => ({ team, pos: index + 1 }))
  const ratingKeys = [
    'Paris Saint-Germain', 'Bayern Munich', 'Barcelona', 'Man United', 'Como', 'Sporting', 'Stuttgart',
    'Man City', 'Betis', 'Lens', 'Aston Villa', 'Dortmund', 'Real Madrid', 'Liverpool', 'Arsenal',
    'AEK', 'Roma', 'Shakhtar', 'Fenerbahçe', 'PSV', 'Villarreal', 'Slavia Praha', 'Brugge', 'Lille',
    'Atlético', 'Inter', 'LASK', 'Napoli', 'Galatasaray', 'Viking', 'Porto', 'RB Leipzig', 'Feyenoord',
    'Sabah FK', 'Slovan', 'Bodø/Glimt',
  ]
  const entries = teamFormEntries('ucl2026', ratingKeys, rows)

  assert.equal(entries.length, 36)
  assert.deepEqual(entries.map(({ team }) => team), rows.map(({ team }) => team))
  assert.deepEqual(entries.map(({ ratingKey }) => ratingKey), ratingKeys)
  assert.deepEqual(teamFormEntries('ucl2026', ratingKeys.slice(0, 35), rows), [])
  assert.deepEqual(teamFormCoverage('ucl2026', ratingKeys.slice(0, 35), rows), {
    complete: false,
    standingsValid: true,
    required: 36,
    available: 35,
    missing: ['Bodo/Glimt'],
  })
})

test('Premier League Team Form is limited to its 20 clubs and reports missing ClubElo ratings', () => {
  assert.equal(typeof teamFormCanonicalName, 'function')
  assert.deepEqual([
    'Coventry City', 'Hull City', 'Ipswich Town', 'Leeds United', 'Newcastle United',
    'Nottingham Forest', 'Tottenham Hotspur',
  ].map(teamFormCanonicalName), ['Coventry', 'Hull', 'Ipswich', 'Leeds', 'Newcastle', 'Forest', 'Tottenham'])
  const clubs = [
    'Manchester City', 'AFC Bournemouth', 'Brighton & Hove Albion',
    ...Array.from({ length: 17 }, (_, index) => `Club ${index + 4}`),
  ]
  const standings = clubs.map((team, index) => ({ team, pos: index + 1 }))
  const ratingKeys = ['Man City', 'Bournemouth', 'Brighton', 'USA']
  const entries = teamFormEntries('epl2026', ratingKeys, standings)

  assert.deepEqual(entries, [
    { team: 'Manchester City', ratingKey: 'Man City' },
    { team: 'AFC Bournemouth', ratingKey: 'Bournemouth' },
    { team: 'Brighton & Hove Albion', ratingKey: 'Brighton' },
  ])
  assert.deepEqual(teamFormCoverage('epl2026', ratingKeys, standings), {
    complete: false,
    standingsValid: true,
    required: 20,
    available: 3,
    missing: clubs.slice(3),
  })
  assert.deepEqual(teamFormEntries('epl2026', ratingKeys, standings.slice(0, 19)), [])

  const hook = readFileSync(new URL('../src/features/team-form/useTeamFormData.ts', import.meta.url), 'utf8')
  const view = readFileSync(new URL('../src/features/team-form/TeamFormView.tsx', import.meta.url), 'utf8')
  assert.match(hook, /competition === 'epl2026'\s*\?\s*teamFormEntries/)
  assert.match(view, /coverage\.required\} Premier-League-Teams/)
})

test('Premier League does not call the World Cup or UCL tournament simulations', () => {
  const view = readFileSync(new URL('../src/features/simulator/SimulatorView.tsx', import.meta.url), 'utf8')
  const queries = readFileSync(new URL('../src/hooks/queries.ts', import.meta.url), 'utf8')
  assert.match(view, /competition === 'epl2026'/)
  assert.match(view, /K\.-o\.-Simulator bildet keine Ligatabelle oder Saison ab/)
  assert.match(queries, /enabled: competition === 'ucl2026' \|\| competition === 'wc2026'/)
})

test('Team Form reports incomplete UCL ratings and only shows World Cup host bonus for WC', () => {
  const view = readFileSync(new URL('../src/features/team-form/TeamFormView.tsx', import.meta.url), 'utf8')
  const hook = readFileSync(new URL('../src/features/team-form/useTeamFormData.ts', import.meta.url), 'utf8')
  assert.match(view, /role="alert"/)
  assert.match(view, /coverage\.available} von \{coverage\.required\}/)
  assert.match(view, /Fehlende Teams: \{coverage\.missing\.join\(', '\)\}/)
  assert.match(view, /competition === 'wc2026' && <p/)
  assert.match(hook, /competition === 'ucl2026'/)
  assert.match(hook, /competition === 'epl2026'/)
  assert.match(hook, /teamFormEntries\(competition, \[\.\.\.allTeams\], standingsRows\)/)
})

test('Premier League loads scoped ClubElo provenance and exposes stale ratings', () => {
  const queries = readFileSync(new URL('../src/hooks/queries.ts', import.meta.url), 'utf8')
  const view = readFileSync(new URL('../src/features/team-form/TeamFormView.tsx', import.meta.url), 'utf8')
  assert.match(queries, /enabled: competition === 'ucl2026' \|\| competition === 'epl2026'/)
  assert.match(view, /staleEplRatings/)
  assert.match(view, /ClubElo-Datenstand für die Premier League ist möglicherweise veraltet/)
})

test('Team Form surfaces stale partial ClubElo refresh while keeping complete last-known ratings usable', () => {
  assert.equal(typeof teamFormSnapshotState, 'function')
  const currentRatings = { complete: true, standingsValid: true, required: 36, available: 36, missing: [] }
  const state = teamFormSnapshotState(currentRatings, {
    status: 'stale',
    error: 'ClubElo snapshot is incomplete',
    coverage: { required: 36, available: 35, missing: ['Bayern Munich'] },
  })
  assert.equal(state.showAlert, true)
  assert.equal(state.showRatings, true)
  assert.equal(state.snapshotAvailable, 35)
  assert.equal(state.snapshotRequired, 36)
  assert.deepEqual(state.snapshotMissing, ['Bayern Munich'])

  const view = readFileSync(new URL('../src/features/team-form/TeamFormView.tsx', import.meta.url), 'utf8')
  assert.match(view, /snapshotMissing/)
  assert.match(view, /letzten vollständigen Ratings/)
})

test('performance counts only actual user tips and refreshes archive data', () => {
  const performance = readFileSync(new URL('../src/features/performance/usePerformanceData.ts', import.meta.url), 'utf8')
  const scoreboard = readFileSync(new URL('../src/features/performance/BotScoreboard.tsx', import.meta.url), 'utf8')
  const view = readFileSync(new URL('../src/features/performance/PerformanceView.tsx', import.meta.url), 'utf8')
  const queries = readFileSync(new URL('../src/hooks/queries.ts', import.meta.url), 'utf8')
  const refresh = queries.slice(queries.indexOf('export const useRefreshData'))

  assert.match(performance, /userCount/)
  assert.match(scoreboard, /tipped: totals\.userCount/)
  assert.match(view, /totals\.correctTendency \/ totals\.userCount/)
  assert.match(refresh, /invalidateQueries\(\{ queryKey: \['archive', competition\] \}\)/)
})

test('performance includes Elo reconstructions and reports their points separately', () => {
  assert.equal(typeof officialPerformance, 'function')

  const result = officialPerformance({
    tracked: {
      metadata: { commence_time: '2026-09-10T18:00:00Z' },
      prediction: {
        algo_reconstructed: false,
        frozen_at: '2026-09-10T17:50:00Z',
        probabilities: { home: 0.6, draw: 0.25, away: 0.15 },
      },
      post_match_result: {
        status: 'completed', actual_score: '2:1', algo_points: 6,
        bot_points: { broker: 5, professor: 6 },
      },
    },
    reconstructed: {
      prediction: { algo_reconstructed: true },
      post_match_result: {
        status: 'completed', algo_points: 10,
        bot_points: { broker: 10, professor: 10 },
      },
    },
    reconstructedMissingPoints: {
      prediction: { algo_reconstructed: true },
      post_match_result: { status: 'completed' },
    },
    pending: {
      prediction: { algo_reconstructed: false },
      post_match_result: { status: 'pending', algo_points: 10 },
    },
  }, ['broker', 'professor'])

  assert.deepEqual(result, {
    algoAllTotal: 16,
    algoAllCount: 2,
    algoAllTendency: 2,
    algoTotal: 6,
    algoCount: 1,
    algoTendency: 1,
    legacyCount: 0,
    legacyPoints: 0,
    legacyTendency: 0,
    reconstructedCount: 1,
    reconstructedPoints: 10,
    reconstructedTendency: 1,
    probabilityCount: 1,
    brierScore: 0.245,
    botStats: {
      broker: { pts: 5, tipped: 1, tendency: 1 },
      professor: { pts: 6, tipped: 1, tendency: 1 },
    },
  })
})

test('official algorithm totals and hit rate exclude Elo reconstructions', () => {
  const result = officialPerformance({
    prematch: {
      metadata: { commence_time: '2026-09-10T18:00:00Z' },
      prediction: {
        algo_reconstructed: false,
        frozen_at: '2026-09-10T17:50:00Z',
        probabilities: { home: 0.6, draw: 0.25, away: 0.15 },
      },
      post_match_result: { status: 'completed', actual_score: '2:1', algo_points: 6 },
    },
    reconstructed: {
      prediction: { algo_reconstructed: true },
      post_match_result: { status: 'completed', algo_points: 10 },
    },
  }, [])

  assert.deepEqual({
    algoTotal: result.algoTotal,
    algoCount: result.algoCount,
    algoTendency: result.algoTendency,
    reconstructedCount: result.reconstructedCount,
    reconstructedPoints: result.reconstructedPoints,
    reconstructedTendency: result.reconstructedTendency,
  }, {
    algoTotal: 6,
    algoCount: 1,
    algoTendency: 1,
    reconstructedCount: 1,
    reconstructedPoints: 10,
    reconstructedTendency: 1,
  })
})

test('overall algorithm points include verified, legacy, and reconstructed tips', () => {
  const result = officialPerformance({
    prematch: {
      metadata: { commence_time: '2026-09-10T18:00:00Z' },
      prediction: {
        frozen_at: '2026-09-10T17:50:00Z',
        probabilities: { home: 0.6, draw: 0.25, away: 0.15 },
      },
      post_match_result: { status: 'completed', actual_score: '2:1', algo_points: 6 },
    },
    legacy: {
      prediction: { top_tip: '1:0' },
      post_match_result: { status: 'completed', algo_points: 8 },
    },
    reconstructed: {
      prediction: { algo_reconstructed: true, top_tip: '1:0' },
      post_match_result: { status: 'completed', algo_points: 10 },
    },
  }, [])

  assert.deepEqual({
    algoAllTotal: result.algoAllTotal,
    algoAllCount: result.algoAllCount,
    algoAllTendency: result.algoAllTendency,
    algoTotal: result.algoTotal,
    algoCount: result.algoCount,
  }, {
    algoAllTotal: 24,
    algoAllCount: 3,
    algoAllTendency: 3,
    algoTotal: 6,
    algoCount: 1,
  })
})

test('performance summary and points race use the complete saved algorithm total', () => {
  const view = readFileSync(new URL('../src/features/performance/PerformanceView.tsx', import.meta.url), 'utf8')
  const race = readFileSync(new URL('../src/features/performance/PointsRaceChart.tsx', import.meta.url), 'utf8')

  assert.match(view, /Algo · \{totals\.algoAllCount\} Tipps gesamt/)
  assert.match(view, /\{totals\.algoAllTotal\}/)
  assert.match(view, /belegte Vorabspiele/)
  assert.match(race, /running\['Algo gesamt'\] \+= entry\.post_match_result\.algo_points \?\? 0/)
  assert.doesNotMatch(race, /filter\(\(\{ entry \}\) => isOfficialPerformanceEntry\(entry\)\)/)
})

test('performance separates unverifiable legacy tips from verified pre-match tips', () => {
  assert.equal(typeof performanceEntryKind, 'function')
  const verified = {
    metadata: { commence_time: '2026-09-10T18:00:00Z' },
    prediction: {
      frozen_at: '2026-09-10T17:50:00Z',
      probabilities: { home: 0.6, draw: 0.25, away: 0.15 },
    },
    post_match_result: { status: 'completed', actual_score: '2:1', algo_points: 6 },
  }
  const legacy = {
    metadata: { commence_time: '2026-09-10T18:00:00Z' },
    prediction: { probabilities: { home: 0.6, draw: 0.25, away: 0.15 } },
    post_match_result: { status: 'completed', actual_score: '2:1', algo_points: 8 },
  }
  const afterKickoff = {
    ...verified,
    prediction: { ...verified.prediction, frozen_at: '2026-09-10T18:01:00Z' },
  }
  const reconstructed = {
    ...verified,
    prediction: { ...verified.prediction, algo_reconstructed: true },
  }

  assert.equal(performanceEntryKind(verified), 'verified')
  assert.equal(performanceEntryKind(legacy), 'legacy')
  assert.equal(performanceEntryKind(afterKickoff), 'legacy')
  assert.equal(performanceEntryKind(reconstructed), 'reconstructed')

  const result = officialPerformance({ verified, legacy, afterKickoff, reconstructed }, [])
  assert.deepEqual({
    algoTotal: result.algoTotal,
    algoCount: result.algoCount,
    legacyPoints: result.legacyPoints,
    legacyCount: result.legacyCount,
    reconstructedPoints: result.reconstructedPoints,
    reconstructedCount: result.reconstructedCount,
    probabilityCount: result.probabilityCount,
    brierScore: result.brierScore,
  }, {
    algoTotal: 6,
    algoCount: 1,
    legacyPoints: 14,
    legacyCount: 2,
    reconstructedPoints: 6,
    reconstructedCount: 1,
    probabilityCount: 1,
    brierScore: 0.245,
  })
})
