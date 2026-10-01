import type {
  Archive, BotSimulation, CompetitionId, CompetitionInfo, CustomBot, CustomBotParams, EloHistory,
  EloRatings, EloRatingsStatus, KnockoutSimulation, MatchIntelligence, MatchesResponse, PoolContext, Prediction, Quota, RawMatch,
  StandingsGroup, UclSimulation,
} from './types'
import { competitionPath } from './competition.mjs'
import { DEFAULT_UCL_SIMULATION_RUNS, uclSimulationPath } from './simulation.mjs'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}${body ? ` — ${body.slice(0, 200)}` : ''}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  competitions: () => request<CompetitionInfo[]>('/competitions'),
  quota: (competition: CompetitionId) => request<Quota>(competitionPath('/quota', competition)),
  matches: (competition: CompetitionId, force = false) =>
    request<MatchesResponse>(competitionPath(`/matches${force ? '?force=true' : ''}`, competition)),
  matchHistory: (competition: CompetitionId, eventId: string) =>
    request<MatchIntelligence>(competitionPath(`/match-history/${encodeURIComponent(eventId)}`, competition)),
  predict: (match: RawMatch, competition: CompetitionId) =>
    request<Prediction>(competitionPath('/predict', competition), {
      method: 'POST',
      body: JSON.stringify({ match, is_ko: Boolean(match.is_ko_phase) }),
    }),
  archive: (competition: CompetitionId) => request<Archive>(competitionPath('/archive', competition)),
  standings: (competition: CompetitionId) => request<StandingsGroup[]>(competitionPath('/standings', competition)),
  eloHistory: (competition: CompetitionId) => request<EloHistory>(competitionPath('/elo_history', competition)),
  eloRatings: (competition: CompetitionId) => request<EloRatings>(competitionPath('/elo_ratings', competition)),
  eloRatingsStatus: (competition: CompetitionId) => request<EloRatingsStatus>(competitionPath('/elo_ratings_status', competition)),
  saveUserTip: (competition: CompetitionId, matchId: string, userTip: string) =>
    request<{ ok: boolean; points_earned: number | null }>(competitionPath('/archive/user_tip', competition), {
      method: 'POST',
      body: JSON.stringify({ match_id: matchId, user_tip: userTip, competition }),
    }),
  poolContext: (competition: CompetitionId, matchId: string) =>
    request<PoolContext>(competitionPath(`/pool-context/${encodeURIComponent(matchId)}`, competition)),
  savePoolContext: (competition: CompetitionId, matchId: string, context: Omit<PoolContext, 'match_id' | 'competition' | 'pool_tip' | 'pool_status'>) =>
    request<PoolContext>(competitionPath(`/pool-context/${encodeURIComponent(matchId)}`, competition), {
      method: 'PUT',
      body: JSON.stringify({ ...context, competition }),
    }),
  customBot: (competition: CompetitionId) => request<CustomBot>(competitionPath('/custom_bot', competition)),
  saveCustomBot: (competition: CompetitionId, name: string, params: CustomBotParams) =>
    request<{ status: string }>(competitionPath('/custom_bot', competition), {
      method: 'POST',
      body: JSON.stringify({ name, params, competition }),
    }),
  simulateBot: (competition: CompetitionId, params: CustomBotParams) =>
    request<BotSimulation>(competitionPath('/custom_bot/simulate', competition), {
      method: 'POST',
      body: JSON.stringify({ params, competition }),
    }),
  simulateKnockout: (competition: CompetitionId, runs = 20_000) =>
    request<KnockoutSimulation | UclSimulation>(competitionPath(`/simulate_knockout?runs=${runs}`, competition)),
  simulateUcl: (competition: CompetitionId, runs = DEFAULT_UCL_SIMULATION_RUNS) =>
    request<UclSimulation>(competitionPath(uclSimulationPath(runs), competition)),
}
