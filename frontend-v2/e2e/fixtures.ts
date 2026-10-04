import { test as base, expect, type Page } from '@playwright/test'
import type { Archive, CompetitionId, Match } from '../src/lib/types'

export const NOW = new Date('2026-10-03T12:00:00Z')
const day = 86_400_000
const uclTeams = ['Bayern Munich', 'Arsenal', 'Paris Saint-Germain', 'Liverpool', 'Borussia Mönchengladbach', 'Club Atlético de Madrid', ...Array.from({ length: 30 }, (_, i) => `Testverein ${i + 1}`)]
const plTeams = ['Arsenal', 'Chelsea', 'Liverpool', 'Manchester City', ...Array.from({ length: 16 }, (_, i) => `Ligaverein ${i + 1}`)]

export function fixture(id: string, home: string, away: string, offset = day): Match {
  const kickoff = new Date(NOW.getTime() + offset).toISOString()
  return {
    id, home_team: home, away_team: away, home_disp: home, away_disp: away,
    raw_match: { id, home_team: home, away_team: away, commence_time: kickoff },
    top_tip: '2:1', model_tip: '2:1', max_xp: 3.9,
    odds: { home: 1.9, draw: 3.4, away: 4.2 }, probabilities: { home: .5, draw: .27, away: .23 },
    status: 'fresh', source: 'odds_api', observed_at: NOW.toISOString(), xg_home: 1.7, xg_away: 1.1,
    home_form: { on_fire: false, status: 'fresh', scope: 'league', source: 'espn', form: ['W', 'D', 'L'], matches: [
      { fixture_id: 'history-1', opponent_name: 'Chelsea', score: '2:1', result: 'W', competition_name: 'Premier League', venue: 'home', played_at: new Date(NOW.getTime() - day).toISOString() },
    ] },
  }
}

function archiveFor(matches: Match[]): Archive {
  return Object.fromEntries(matches.map(match => [match.id, {
    metadata: { home_team: match.home_team, away_team: match.away_team, home_disp: match.home_team, away_disp: match.away_team, commence_time: match.raw_match?.commence_time, is_ko_phase: false },
    prediction: { top_tip: '2:1', max_xp: 3.9, user_tip: null },
    post_match_result: { status: 'pending' },
  }]))
}

export async function installApi(page: Page) {
  const matches: Record<CompetitionId, Match[]> = {
    ucl2026: [fixture('ucl-next', uclTeams[0], uclTeams[1]), fixture('ucl-long', uclTeams[4], uclTeams[5], day * 2)],
    epl2026: [fixture('pl-next', plTeams[0], plTeams[1])],
    wc2026: [fixture('wc-next', 'England', 'Switzerland')],
  }
  const archive = Object.fromEntries(Object.entries(matches).map(([comp, items]) => [comp, archiveFor(items)])) as Record<CompetitionId, Archive>
  for (const [competition, items] of Object.entries(matches)) {
    const first = items[0]
    for (let i = 1; i <= 2; i++) {
      const past = fixture(`${competition}-result-${i}`, first.home_team, first.away_team, -day * i)
      const entry = archiveFor([past])[past.id]
      entry.prediction.user_tip = '2:1'
      entry.prediction.frozen_at = new Date(NOW.getTime() - day * i - 10 * 60_000).toISOString()
      entry.prediction.probabilities = { home: .5, draw: .27, away: .23 }
      entry.pre_match_snapshot = { timestamp_recorded: entry.prediction.frozen_at }
      entry.post_match_result = { status: 'completed', actual_score: '2:1', points_earned: 5, algo_points: 5 }
      archive[competition][past.id] = entry
    }
  }
  const state = {
    matches, archive, failArchive: false, failHistory: false, failSave: 0, unavailableRefresh: false,
    saveGate: undefined as Promise<void> | undefined,
    matchesGate: undefined as Promise<void> | undefined,
    saves: [] as { match_id: string; user_tip: string; competition: CompetitionId }[],
    unexpected: [] as string[],
  }
  await page.route('**/api/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const endpoint = url.pathname.slice('/api/'.length)
    const competition = (url.searchParams.get('competition') ?? 'ucl2026') as CompetitionId
    const teams = competition === 'ucl2026' ? uclTeams : competition === 'epl2026' ? plTeams : ['England', 'Switzerland', 'France', 'Germany']
    const respond = (json: unknown, status = 200) => route.fulfill({ json, status })
    if (endpoint === 'competitions') return respond([
      { id: 'ucl2026', short_name: 'UCL 2026/27', display_name: 'UEFA Champions League 2026/27' },
      { id: 'epl2026', short_name: 'PL 2026/27', display_name: 'Premier League 2026/27' },
      { id: 'wc2026', short_name: 'WM 2026', display_name: 'FIFA World Cup 2026' },
    ])
    if (endpoint === 'matches') {
      await state.matchesGate
      if (state.unavailableRefresh && url.searchParams.get('force') === 'true') return respond({ status: 'unavailable', data: [], error: 'Cache temporarily unavailable' })
      return respond(matches[competition])
    }
    if (endpoint === 'archive') return state.failArchive ? respond({ detail: 'Archive unavailable' }, 503) : respond(archive[competition])
    if (endpoint === 'archive/user_tip') {
      const tip = request.postDataJSON()
      state.saves.push(tip)
      await state.saveGate
      if (state.failSave) return respond({ detail: 'Save rejected' }, state.failSave)
      archive[competition][tip.match_id].prediction.user_tip = tip.user_tip
      return respond({ ok: true })
    }
    if (endpoint === 'predict') return respond({ model_tip: '2:1', top_tip: '2:1', probabilities: { home: .5, draw: .27, away: .23 }, matrix: { 2: { 1: .11 } }, xp_tips: [{ Tipp: '2:1', xP: 3.9 }], status: 'fresh', source: 'odds_api', observed_at: NOW.toISOString() })
    if (endpoint === 'standings') return respond([{ name: 'Ligaphase', rows: teams.map((team, i) => ({ team, pos: i + 1, p: 2, w: 1, d: 1, l: 0, gf: 3, ga: 1, gd: 2, pts: 4 })) }])
    if (endpoint === 'elo_ratings') return respond(Object.fromEntries(teams.map((team, i) => [team, { elo: 2000 - i * 10 }])))
    if (endpoint === 'elo_history') return respond(Object.fromEntries(teams.map((team, i) => [team, [
      { timestamp: (NOW.getTime() - day * 7) / 1000, elo: 1950 - i * 10, match_id: 'start' },
      { timestamp: NOW.getTime() / 1000, elo: 2000 - i * 10, match_id: 'next' },
    ]])))
    if (endpoint === 'elo_ratings_status') return respond({ status: 'fresh', observed_at: NOW.toISOString(), source: 'clubelo', coverage: { required: teams.length, available: teams.length, missing: [] } })
    if (endpoint === 'quota') return respond({ odds: { remaining: 100, used: 0 }, football: { remaining: 100, used: 0 } })
    if (endpoint === 'custom_bot/simulate') return respond({ total_points: 0, matches: 0, tendency_rate: 0, breakdown: [] })
    if (endpoint === 'custom_bot') return respond({ exists: false })
    if (endpoint.startsWith('pool-context/')) return respond({ match_id: endpoint.split('/').at(-1), competition, user_points: 0, leader_points: 0, remaining_srf_max_points: 1, tip_counts: {}, pool_status: 'unavailable' })
    if (endpoint.startsWith('match-history/')) return state.failHistory ? respond({ detail: 'History unavailable' }, 503) : respond({ status: 'unavailable', lineups: {} })
    if (endpoint.startsWith('odds-history/')) return respond({ snapshots: [] })
    if (endpoint === 'model-evaluation') return respond({ competition, completed_count: 2, captured_count: 2, common_sample_count: 2, coverage_rate: 1, exclusions: {}, metrics: { model: { brier_score: .25, log_loss: .5 }, market: { brier_score: .25, log_loss: .5 }, elo: { brier_score: .25, log_loss: .5 } } })
    if (endpoint === 'model-comparison') return respond({ counts: { total_completed: 0, verified_model: 0, paired: 0, missing_baselines: 0, excluded: 0 }, models: [] })
    if (endpoint.startsWith('simulate')) return respond({ status: 'unavailable', n_runs: 0, teams: [], results: [], bracket: [], round_labels: [] })
    state.unexpected.push(`${request.method()} ${endpoint}`)
    return respond({ detail: 'Unconfigured test endpoint' }, 404)
  })
  return state
}

export const test = base.extend<{ api: Awaited<ReturnType<typeof installApi>> }>({
  api: async ({ page }, use) => {
    await page.clock.setFixedTime(NOW)
    const api = await installApi(page)
    await use(api)
    expect(api.unexpected).toEqual([])
  },
})
export { expect }

export async function chooseCompetition(page: Page, competition: CompetitionId) {
  const mobile = (page.viewportSize()?.width ?? 1440) < 1024
  if (mobile) await page.getByRole('button', { name: 'Mehr', exact: true }).click()
  await page.getByLabel('Wettbewerb', { exact: true }).filter({ visible: true }).selectOption(competition)
  if (mobile) await page.getByRole('button', { name: 'Menü schliessen' }).click()
}
