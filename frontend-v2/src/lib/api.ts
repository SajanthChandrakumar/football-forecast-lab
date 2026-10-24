import type {
  Archive, BotSimulation, CompetitionId, CompetitionInfo, CustomBot, CustomBotParams, EloHistory,
  EloRatings, EloRatingsStatus, KnockoutSimulation, MatchIntelligence, MatchesResponse, PoolContext, Prediction, Quota, RawMatch,
  StandingsGroup, UclSimulation, UclSimulationProcessing, UclSimulationResponse, ModelEvaluation, ManualRefreshResult,
} from './types'
import { competitionPath } from './competition.mjs'
import { DEFAULT_UCL_SIMULATION_RUNS, uclSimulationPath } from './simulation.mjs'

let editorToken = ""
let editorKeyRequest: Promise<string | null> | null = null

function askForEditorKey(): Promise<string | null> {
  if (!editorKeyRequest) {
    editorKeyRequest = new Promise<string | null>((resolve) => {
      window.dispatchEvent(new CustomEvent('editor-key-required', { detail: { resolve } }))
    }).finally(() => { editorKeyRequest = null })
  }
  return editorKeyRequest ?? Promise.resolve(null)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  headers.set('Content-Type', 'application/json')
  const sharedWrite = (init?.method === 'POST' || init?.method === 'PUT') &&
    /^\/(archive\/(user_tip|historical_tip)|custom_bot|pool-context\/[^?]+)(\?|$)/.test(path)
  const requestedCompetition = new URLSearchParams(path.split('?')[1] ?? '').get('competition')
  if (sharedWrite) {
    editorToken ||= requestedCompetition === 'epl2026' || requestedCompetition === 'ucl2026'
      ? (await askForEditorKey())?.trim() ?? ''
      : window.prompt('Editor-Schlüssel zum Speichern eingeben:')?.trim() ?? ''
    if (!editorToken) throw new Error('Speichern benötigt einen Editor-Schlüssel.')
    headers.set('Authorization', `Bearer ${editorToken}`)
  }
  const timeoutSignal = AbortSignal.timeout(12_000)
  const signal = init?.signal ? AbortSignal.any([init.signal, timeoutSignal]) : timeoutSignal
  let res: Response
  try {
    res = await fetch(`/api${path}`, { ...init, headers, signal })
  } catch (error) {
    if (timeoutSignal.aborted && !init?.signal?.aborted) throw new Error('Die Anfrage dauert zu lange. Bitte erneut versuchen.')
    throw error
  }
  if (sharedWrite && res.status === 401) editorToken = ''
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}${body ? ` — ${body.slice(0, 200)}` : ''}`)
  }
  return res.json() as Promise<T>
}

export class ManualRefreshError extends Error {
  retryAfter: number
  constructor(message: string, retryAfter = 0) {
    super(message)
    this.retryAfter = retryAfter
  }
}

function waitForRetry(milliseconds: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) { reject(signal.reason); return }
    const finish = () => { signal?.removeEventListener('abort', abort); resolve() }
    const timer = window.setTimeout(finish, milliseconds)
    const abort = () => { window.clearTimeout(timer); signal?.removeEventListener('abort', abort); reject(signal?.reason) }
    signal?.addEventListener('abort', abort, { once: true })
  })
}

function isProcessingSimulation(data: UclSimulationResponse): data is UclSimulationProcessing {
  return data.status === 'processing'
}

export const api = {
  manualRefresh: async (competition: CompetitionId, token: string): Promise<ManualRefreshResult> => {
    let res: Response
    const timeoutSignal = AbortSignal.timeout(90_000)
    try {
      res = await fetch(`/api${competitionPath('/internal/manual-refresh', competition)}`, {
        method: 'POST', headers: { Authorization: `Bearer ${token}` }, signal: timeoutSignal,
      })
    } catch {
      throw new ManualRefreshError(timeoutSignal.aborted
        ? 'Der Datenabruf dauert zu lange. Bitte später erneut versuchen.'
        : 'Verbindung fehlgeschlagen. Bitte erneut versuchen.')
    }
    if (!res.ok) {
      const messages: Record<number, string> = {
        401: 'Admin-Schlüssel ist ungültig.',
        429: 'Bitte warte kurz vor dem nächsten Abruf.',
        503: 'API-Aktualisierung ist nicht eingerichtet oder derzeit nicht verfügbar.',
      }
      const body = await res.json().catch(() => null)
      const detail = typeof body?.detail === 'string' ? body.detail : undefined
      const retryAfter = Number(res.headers.get('Retry-After'))
      throw new ManualRefreshError(detail ?? messages[res.status] ?? 'Aktualisierung fehlgeschlagen.',
        res.status === 429 && Number.isFinite(retryAfter) && retryAfter > 0 ? Math.ceil(retryAfter) : 0)
    }
    return res.json() as Promise<ManualRefreshResult>
  },
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
  saveHistoricalTip: (competition: CompetitionId, matchId: string, userTip: string) =>
    request<{ ok: boolean; points_earned: number | null }>(competitionPath('/archive/historical_tip', competition), {
      method: 'POST', body: JSON.stringify({ match_id: matchId, user_tip: userTip, competition }),
    }),
  archive: (competition: CompetitionId) => request<Archive>(competitionPath('/archive', competition)),
  modelEvaluation: (competition: CompetitionId) => request<ModelEvaluation>(competitionPath('/model-evaluation', competition)),
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
  simulateUcl: async (competition: CompetitionId, runs = DEFAULT_UCL_SIMULATION_RUNS, signal?: AbortSignal): Promise<UclSimulationResponse> => {
    const deadline = Date.now() + 30_000
    while (true) {
      const data = await request<UclSimulationResponse>(competitionPath(uclSimulationPath(runs), competition), { signal })
      if (!isProcessingSimulation(data)) return data
      const remaining = deadline - Date.now()
      if (remaining <= 0) return { ...data, timed_out: true }
      const delay = Math.min(remaining, Math.max(0.25, Math.min(data.retry_after ?? 3, 10)) * 1000)
      await waitForRetry(delay, signal ?? undefined)
    }
  },
}
