// Backend response shapes — mirrors src/api.py + routes/services.
export type CompetitionId = string

export interface CompetitionInfo {
  id: CompetitionId
  display_name: string
  short_name: string
  display?: { name: string; short_name: string }
  season?: string
  ruleset?: string
}

export interface Odds {
  home: number
  draw: number
  away: number
  over25?: number
  under25?: number
}

export interface Probabilities {
  home: number
  draw: number
  away: number
}

export type TeamFormStatus = 'fresh' | 'stale' | 'unavailable'

export interface TeamFormMatch {
  fixture_id: string
  played_at: string
  competition_name: string
  opponent_id?: string
  opponent_name: string
  venue: 'home' | 'away'
  goals_for?: number
  goals_against?: number
  score: string
  result: 'W' | 'D' | 'L'
}

export interface TeamForm {
  form: ('W' | 'D' | 'L')[]
  on_fire: boolean
  status?: TeamFormStatus
  source?: string
  observed_at?: string | null
  error?: string | null
  matches?: TeamFormMatch[]
}

export interface BotTip {
  tip: string
  xp?: number
}

export type BotKey = 'broker' | 'professor' | 'sniper' | 'gambler'

export interface RawMatch {
  id: string
  home_team?: string
  away_team?: string
  round?: string
  commence_time?: string
  match_context?: MatchContext
  stage?: string
  leg?: string
  tie_id?: string
  first_leg_score?: string | null
  extra_time_eligible?: boolean
  [key: string]: unknown
}

export interface MatchContext {
  competition?: CompetitionId
  stage?: string
  tie_id?: string
  leg?: string
  first_leg_score?: string | null
  score_90?: string | null
  score_aet?: string | null
  shootout_winner?: string | null
  extra_time_eligible?: boolean
  commence_time?: string
  [key: string]: unknown
}

export interface Match {
  id: string
  home_team: string
  away_team: string
  home_disp: string
  away_disp: string
  home_logo?: string | null
  away_logo?: string | null
  logo?: string | null
  odds?: Odds
  odds_observed_at?: string | null
  odds_provenance?: Record<string, unknown>
  probabilities?: Probabilities | null
  top_tip: string
  model_tip?: string | null
  pool_tip?: string | null
  pool_status?: string
  status?: string
  source_status?: string
  source?: string | null
  observed_at?: string | null
  source_mode?: string | null
  model_version?: string | null
  input_provenance?: Record<string, unknown>
  provenance?: Record<string, unknown>
  xg_home?: number | null
  xg_away?: number | null
  context?: MatchContext
  match_context?: MatchContext
  max_xp: number
  edge_home?: number | null
  market_home_share?: number | null
  elo_home_share?: number | null
  home_form?: TeamForm
  away_form?: TeamForm
  h2h?: Record<string, number>
  lineup_diff?: Record<string, { starters: Record<string, string>; missing: string[] }>
  bots?: Partial<Record<BotKey, BotTip>>
  home_team_id?: number
  away_team_id?: number
  is_ko_phase?: boolean
  stage?: string
  tie_id?: string
  leg?: string
  first_leg_score?: string | null
  score_90?: string | null
  score_aet?: string | null
  shootout_winner?: string | null
  extra_time_eligible?: boolean
  completed?: boolean
  actual_score?: string | null
  raw_match: RawMatch
}

export interface UnavailablePayload {
  status: 'unavailable' | 'failed' | 'stale' | 'fresh'
  source: string
  observed_at?: string | null
  error?: string
  data?: Match[]
}

export type MatchesResponse = Match[] | UnavailablePayload

export interface XpTip {
  Tipp: string
  xP: number
}

export interface Prediction {
  xg_home?: number | null
  xg_away?: number | null
  max_prob?: number
  top_tip?: string | null
  model_tip?: string | null
  pool_tip?: string | null
  pool_status?: string
  status?: string
  source_status?: string
  source?: string | null
  observed_at?: string | null
  source_mode?: string | null
  model_version?: string | null
  input_provenance?: Record<string, unknown>
  provenance?: Record<string, unknown>
  probabilities?: Probabilities | null
  /** Dict-of-dicts keyed by home/away goal count (backend serializes the DataFrame). */
  matrix?: Record<number, Record<number, number>>
  xp_tips?: XpTip[]
}

export interface ArchiveEntry {
  metadata: {
    home_team: string
    away_team: string
    home_disp: string
    away_disp: string
    is_ko_phase: boolean
    commence_time?: string | null
  }
  pre_match_snapshot?: {
    timestamp_recorded?: string
    [key: string]: unknown
  } | null
  prediction: {
    top_tip: string | null
    model_tip?: string | null
    pool_tip?: string | null
    pool_status?: string
    max_xp: number | null
    status?: string
    source_status?: string
    source?: string | null
    observed_at?: string | null
    source_mode?: string | null
    model_version?: string | null
    input_provenance?: Record<string, unknown>
    provenance?: Record<string, unknown>
    user_tip?: string | null
    algo_reconstructed?: boolean
    bots?: Partial<Record<BotKey, BotTip>>
  }
  post_match_result: {
    status: 'pending' | 'completed'
    actual_score?: string | null
    points_earned?: number | null
    algo_points?: number | null
    bot_points?: Partial<Record<BotKey, number | null>>
  }
}

export type Archive = Record<string, ArchiveEntry>

export interface EloHistoryPoint {
  timestamp: number
  match_id: string
  elo: number
}

export type EloHistory = Record<string, EloHistoryPoint[]>

export type EloRatings = Record<string, { team_code?: string; elo: number }>

export interface EloRatingsStatus {
  status: 'fresh' | 'stale' | 'failed' | 'unavailable'
  source: string
  observed_at?: string | null
  error?: string | null
  coverage?: {
    required: number
    available: number
    missing: string[]
    errors?: Record<string, string>
  } | null
}

export interface Quota {
  odds: { remaining: string | number; used: string | number }
  football: { remaining: string | number; used: string | number; limit?: string | number }
}

export interface CustomBotParams {
  market_weight: number
  risk: number
  draw_bias: number
  underdog_bias: number
}

export interface CustomBot {
  exists: boolean
  name?: string
  params?: CustomBotParams
}

export interface PoolContext {
  match_id: string
  competition: CompetitionId
  user_points: number
  leader_points: number
  remaining_srf_max_points: number
  tip_counts: Record<string, number>
  pool_tip?: string | null
  pool_status: string
}

export interface BotSimulation {
  total_points: number
  matches: number
  tendency_rate: number
  breakdown: { match_id: string; points: number }[]
}

export interface SyncResult {
  status: 'success' | 'info' | 'error'
  updates?: number
  message?: string
}

export interface KnockoutTeamResult {
  team: string
  elo: number
  reached_qf: number
  reached_sf: number
  reached_final: number
  champion: number
}

export interface KnockoutSimulation {
  status?: string
  warnings?: string[]
  n_runs: number
  bracket: { home: string; away: string }[]
  round_labels: string[]
  results: KnockoutTeamResult[]
}

export interface UclSimulationTeam {
  team: string
  expected_points: number
  expected_rank: number
  top8: number
  top24: number
  round_of_16: number
  quarterfinal: number
  semifinal: number
  final: number
  champion: number
}

export interface UclSimulation {
  status: string
  error?: string
  reason?: string
  runs?: number
  n_runs: number
  seed?: number
  table_version?: string
  coefficient_version?: string
  coefficient_provenance?: Record<string, unknown>
  provenance?: Record<string, unknown>
  official_order?: string[]
  ranking_source?: string
  warnings?: string[]
  teams: UclSimulationTeam[]
  results: UclSimulationTeam[]
  bracket?: Record<string, unknown>
}

export interface StandingsRow {
  pos?: number
  team: string
  logo?: string | null
  p?: number
  w?: number
  d?: number
  l?: number
  gf?: number
  ga?: number
  gd?: number
  pts?: number
  [key: string]: unknown
}

export interface StandingsGroup {
  name?: string
  rows: StandingsRow[]
}

export interface ModelEvaluation {
  competition: CompetitionId
  completed_count: number
  captured_count: number
  common_sample_count: number
  coverage_rate: number | null
  exclusions: Record<string, number>
  metrics: Record<'model' | 'market' | 'elo', { brier_score: number | null; log_loss: number | null }>
  metric_definitions: { brier_score: string; brier_range: [number, number]; log_loss: string; probability_floor: number }
}
