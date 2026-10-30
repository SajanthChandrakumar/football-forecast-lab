import { useCallback, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useAppState } from '../state/AppState'
import type { Archive, ArchiveEntry, CompetitionId, CustomBotParams, KnockoutSimulation, Match, MatchDetailResponse, MatchesResponse, PoolContext, ProcessingPayload, RawMatch, UclSimulationResponse, UnavailablePayload } from '../lib/types'

const MAX_PREPARATION_POLLS = 4
const retryDelay = (seconds?: number) => Math.max(250, Math.min(seconds ?? 2, 10) * 1000)

/** The cache can hold the same fixture under two ids (provider switch) —
 *  keep the entry with the richer prediction per team-pair + kickoff. */
function dedupeMatches(matches: Match[]): Match[] {
  const byKey = new Map<string, Match>()
  for (const m of matches) {
    const key = `${m.home_team}|${m.away_team}|${m.raw_match?.commence_time ?? ''}`
    const prev = byKey.get(key)
    if (!prev || (prev.top_tip === 'N/A' && m.top_tip !== 'N/A') || (prev.max_xp ?? 0) < (m.max_xp ?? 0)) {
      byKey.set(key, m)
    }
  }
  return [...byKey.values()]
}

type MatchListData = {
  matches: Match[]
  status?: UnavailablePayload['status'] | 'processing'
  source?: string
  observed_at?: string | null
  error?: string
  processingAttempts?: number
  retry_after?: number
  reason?: string
}

function normalizeMatches(result: MatchesResponse, previous?: MatchListData, processingAttempts = 0): MatchListData {
  if (Array.isArray(result)) return { matches: result }
  if (result.status === 'processing') {
    return { ...previous, matches: previous?.matches ?? result.data, status: result.status, source: result.source,
      retry_after: result.retry_after, reason: result.reason, processingAttempts }
  }
  return { ...result, matches: result.data ?? [] }
}

function isProcessingMatch(result: MatchDetailResponse): result is ProcessingPayload {
  return !('id' in result) && result.status === 'processing'
}

export const useMatches = (overview = false, enabled = true) => {
  const { competition } = useAppState()
  const qc = useQueryClient()
  const processingAttempts = useRef(0)
  const queryKey = overview && competition !== 'wc2026' ? ['matches', competition, 'overview'] : ['matches', competition]
  const query = useQuery({
    queryKey,
    queryFn: async ({ signal }) => {
      const previous = qc.getQueryData<MatchListData>(queryKey)
      const result = await api.matches(competition, false, overview && competition !== 'wc2026', signal)
      if (!Array.isArray(result) && result.status === 'processing') processingAttempts.current += 1
      else processingAttempts.current = 0
      if (!Array.isArray(result) && (result.status === 'unavailable' || result.status === 'failed') && previous?.matches.length) {
        return { ...previous, status: result.status, source: result.source, observed_at: result.observed_at, error: result.error, processingAttempts: 0 }
      }
      return normalizeMatches(result, previous, processingAttempts.current)
    },
    enabled,
    staleTime: 60_000,
    refetchOnMount: 'always',
    retry: false,
    refetchInterval: (current) => current.state.data?.status === 'processing'
      ? (current.state.data.processingAttempts ?? 0) < MAX_PREPARATION_POLLS ? retryDelay(current.state.data.retry_after) : false
      : overview && competition !== 'wc2026' ? 15_000 : 60_000,
    select: (result) => ({ ...result, matches: dedupeMatches(result.matches) }),
  })
  const { refetch: refetchQuery, ...queryState } = query
  const refetch = useCallback(() => { processingAttempts.current = 0; return refetchQuery() }, [refetchQuery])
  return { ...queryState, refetch, data: query.data?.matches, availability: query.data }
}

type MatchQueryData = { match?: Match; processing?: ProcessingPayload; processingAttempts: number }

export const useMatchCore = (matchId: string | undefined, enabled = true) => {
  const { competition } = useAppState()
  const qc = useQueryClient()
  const processingAttempts = useRef(0)
  const queryKey = ['matches', competition, 'core', matchId]
  const query = useQuery<MatchQueryData>({
    queryKey,
    enabled: enabled && Boolean(matchId),
    queryFn: async ({ signal }) => {
      const previous = qc.getQueryData<MatchQueryData>(queryKey)
      const result = await api.matchCore(competition, matchId!, signal)
      if (isProcessingMatch(result)) {
        processingAttempts.current += 1
        return { match: previous?.match, processing: result, processingAttempts: processingAttempts.current }
      }
      processingAttempts.current = 0
      return { match: result, processingAttempts: 0 }
    },
    staleTime: 60_000,
    refetchOnMount: 'always',
    retry: false,
    refetchInterval: (current) => current.state.data?.processing
      ? current.state.data.processingAttempts < MAX_PREPARATION_POLLS ? retryDelay(current.state.data.processing.retry_after) : false
      : 15_000,
  })
  const { refetch: refetchQuery, ...queryState } = query
  const refetch = useCallback(() => { processingAttempts.current = 0; return refetchQuery() }, [refetchQuery])
  return { ...queryState, refetch, data: query.data?.match, processing: query.data?.processing }
}

type MatchAnalysisData = { match?: Match; processing?: ProcessingPayload; processingAttempts: number }

export const useMatchAnalysis = (matchId: string | undefined, viewVersion: string | undefined, routeMatchId: string | undefined, enabled: boolean) => {
  const { competition } = useAppState()
  const qc = useQueryClient()
  const processingAttempts = useRef(0)
  const queryKey = ['matches', competition, 'analysis', matchId, viewVersion]
  const coreKey = ['matches', competition, 'core', routeMatchId]
  const query = useQuery<MatchAnalysisData>({
    queryKey,
    enabled: enabled && Boolean(matchId && viewVersion && routeMatchId),
    queryFn: async ({ signal }) => {
      const previous = qc.getQueryData<MatchAnalysisData>(queryKey)
      const result = await api.matchAnalysis(competition, matchId!, signal)
      if (isProcessingMatch(result)) {
        processingAttempts.current += 1
        return { match: previous?.match, processing: result, processingAttempts: processingAttempts.current }
      }
      if (result.id !== matchId || result.view_version !== viewVersion) {
        processingAttempts.current = 0
        await qc.invalidateQueries({ queryKey: coreKey, exact: true })
        throw new Error('Die Spieldaten wurden während des Ladens aktualisiert. Bitte versuche die Analyse erneut.')
      }
      processingAttempts.current = 0
      return { match: result, processingAttempts: 0 }
    },
    staleTime: 60_000,
    refetchOnMount: 'always',
    retry: false,
    refetchInterval: (current) => current.state.data?.processing
      ? current.state.data.processingAttempts < MAX_PREPARATION_POLLS ? retryDelay(current.state.data.processing.retry_after) : false
      : 60_000,
  })
  const { refetch: refetchQuery, ...queryState } = query
  const refetch = useCallback(() => { processingAttempts.current = 0; return refetchQuery() }, [refetchQuery])
  return { ...queryState, refetch, data: query.data?.match, processing: query.data?.processing }
}

export const useMatchHistory = (eventId: string, enabled: boolean) => {
  const { competition } = useAppState()
  return useQuery({
    queryKey: ['matchHistory', competition, eventId],
    queryFn: () => api.matchHistory(competition, eventId),
    enabled: enabled && Boolean(eventId),
    staleTime: 300_000,
    retry: false,
  })
}

export const useArchive = (enabled = true, matchId?: string) => {
  const { competition } = useAppState()
  return useQuery({
    queryKey: matchId ? ['archive', competition, matchId] : ['archive', competition],
    queryFn: ({ signal }) => api.archive(competition, matchId, signal),
    enabled,
    staleTime: 60_000,
    refetchInterval: 60_000,
    refetchOnMount: matchId ? 'always' : undefined,
    retry: false,
  })
}

export const useModelEvaluation = () => {
  const { competition } = useAppState()
  return useQuery({ queryKey: ['modelEvaluation', competition], queryFn: () => api.modelEvaluation(competition), staleTime: 60_000, refetchInterval: 60_000 })
}

export const useStandings = () => {
  const { competition } = useAppState()
  return useQuery({ queryKey: ['standings', competition], queryFn: () => api.standings(competition), staleTime: 60_000 })
}

export const useDataStatus = () => {
  const { competition } = useAppState()
  return useQuery({ queryKey: ['dataStatus', competition], queryFn: ({ signal }) => api.dataStatus(competition, signal), staleTime: 60_000, refetchInterval: 60_000, retry: false })
}

export const useQuota = () => {
  const { competition } = useAppState()
  return useQuery({ queryKey: ['quota', competition], queryFn: () => api.quota(competition), staleTime: 60_000 })
}

export const useEloHistory = () => {
  const { competition } = useAppState()
  return useQuery({ queryKey: ['eloHistory', competition], queryFn: () => api.eloHistory(competition), staleTime: 300_000 })
}

export const useEloRatings = () => {
  const { competition } = useAppState()
  return useQuery({ queryKey: ['eloRatings', competition], queryFn: () => api.eloRatings(competition), staleTime: 300_000 })
}

export const useEloRatingsStatus = () => {
  const { competition } = useAppState()
  return useQuery({
    queryKey: ['eloRatingsStatus', competition],
    queryFn: () => api.eloRatingsStatus(competition),
    enabled: competition === 'ucl2026' || competition === 'epl2026',
    staleTime: 300_000,
  })
}

export const useKnockoutSimulation = () => {
  const { competition } = useAppState()
  return useQuery<UclSimulationResponse | KnockoutSimulation>({
    queryKey: ['knockoutSim', competition],
    queryFn: ({ signal }) => competition === 'ucl2026' ? api.simulateUcl(competition, undefined, signal) : api.simulateKnockout(competition),
    enabled: competition === 'ucl2026' || competition === 'wc2026',
    staleTime: 300_000,
  })
}

export const useCustomBot = () => {
  const { competition } = useAppState()
  return useQuery({ queryKey: ['customBot', competition], queryFn: () => api.customBot(competition), staleTime: 300_000, retry: false })
}

export const usePoolContext = (matchId: string | undefined) => {
  const { competition } = useAppState()
  return useQuery({
    queryKey: ['poolContext', competition, matchId],
    queryFn: () => api.poolContext(competition, matchId!),
    enabled: Boolean(matchId),
    staleTime: 60_000,
  })
}

export const usePredict = () => {
  const { competition } = useAppState()
  return useMutation({
    mutationFn: ({ match, targetCompetition = competition }: { match: RawMatch; targetCompetition?: CompetitionId }) => api.predict(match, targetCompetition),
  })
}

export const useSaveUserTip = () => {
  const { competition } = useAppState()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ matchId, tip, targetCompetition, historical = false }: { matchId: string; tip: string; targetCompetition?: typeof competition; historical?: boolean }) =>
      historical ? api.saveHistoricalTip(targetCompetition ?? competition, matchId, tip) : api.saveUserTip(targetCompetition ?? competition, matchId, tip),
    onSuccess: (result, { matchId, tip, targetCompetition }) => {
      const savedCompetition = targetCompetition ?? competition
      const acceptedMatchId = result.match_id ?? matchId
      const canonicalMatchId = result.canonical_match_id ?? acceptedMatchId
      const acceptedEntry: ArchiveEntry | undefined = result.match_id ? result.archive_entry : undefined
      for (const [queryKey, current] of qc.getQueriesData<Archive>({ queryKey: ['archive', savedCompetition] })) {
        if (!current) continue
        const isFullArchive = queryKey.length === 2
        const isMatchingGameArchive = queryKey.length === 3 && (queryKey[2] === canonicalMatchId || queryKey[2] === matchId)
        if (acceptedEntry && isFullArchive) {
          qc.setQueryData<Archive>(queryKey, { ...current, [acceptedMatchId]: acceptedEntry })
          continue
        }
        if (acceptedEntry && isMatchingGameArchive) {
          qc.setQueryData<Archive>(queryKey, { ...current, [canonicalMatchId]: acceptedEntry })
          continue
        }

        // Older servers only return ok/points. Patch a saved row when one is already cached,
        // but never fabricate the rest of a newly-created archive record.
        const existingId = current[acceptedMatchId] ? acceptedMatchId : current[canonicalMatchId] ? canonicalMatchId : current[matchId] ? matchId : undefined
        const existing = existingId ? current[existingId] : undefined
        if (existing && existingId && (isFullArchive || isMatchingGameArchive)) {
          qc.setQueryData<Archive>(queryKey, {
            ...current,
            [existingId]: { ...existing, prediction: { ...existing.prediction, user_tip: tip } },
          })
        }
      }

      const acceptedTip = acceptedEntry?.prediction.user_tip
      if (['epl2026', 'ucl2026'].includes(savedCompetition) && acceptedEntry && result.match_id && typeof acceptedTip === 'string') {
        for (const [queryKey, current] of qc.getQueriesData<unknown>({ queryKey: ['matches', savedCompetition] })) {
          if (!current || !Array.isArray(queryKey)) continue
          if ((queryKey.length === 2 || (queryKey.length === 3 && queryKey[2] === 'overview')) && typeof current === 'object' && 'matches' in current) {
            const listData = current as MatchListData
            qc.setQueryData(queryKey, {
              ...listData,
              matches: listData.matches.map(match => match.id === canonicalMatchId ? { ...match, user_tip: acceptedTip } : match),
            })
          } else if (queryKey[2] === 'core' && typeof current === 'object' && 'match' in current) {
            const detailData = current as MatchQueryData
            if (detailData.match?.id === canonicalMatchId) qc.setQueryData(queryKey, { ...detailData, match: { ...detailData.match, user_tip: acceptedTip } })
          } else if (queryKey[2] === 'analysis' && typeof current === 'object' && 'match' in current) {
            const detailData = current as MatchAnalysisData
            if (detailData.match?.id === canonicalMatchId) qc.setQueryData(queryKey, { ...detailData, match: { ...detailData.match, user_tip: acceptedTip } })
          }
        }
      }
      qc.invalidateQueries({ queryKey: ['archive', savedCompetition] })
      qc.invalidateQueries({ queryKey: ['matches', savedCompetition] })
    },
  })
}

export const useSavePoolContext = () => {
  const { competition } = useAppState()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ matchId, context }: { matchId: string; context: Omit<PoolContext, 'match_id' | 'competition' | 'pool_tip' | 'pool_status'> }) =>
      api.savePoolContext(competition, matchId, context),
    onSuccess: (_, { matchId }) => {
      qc.invalidateQueries({ queryKey: ['poolContext', competition, matchId] })
      qc.invalidateQueries({ queryKey: ['matches', competition] })
      qc.invalidateQueries({ queryKey: ['archive', competition] })
    },
  })
}

export const useSaveCustomBot = () => {
  const { competition } = useAppState()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ name, params }: { name: string; params: CustomBotParams }) =>
      api.saveCustomBot(competition, name, params),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['customBot', competition] })
    },
  })
}

export const useSimulateBot = () => {
  const { competition } = useAppState()
  return useMutation({ mutationFn: (params: CustomBotParams) => api.simulateBot(competition, params) })
}

export const useRefreshData = () => {
  const { competition } = useAppState()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const overview = competition !== 'wc2026'
      const key = overview ? ['matches', competition, 'overview'] : ['matches', competition]
      const result = await api.matches(competition, true, overview)
      if (!Array.isArray(result) && result.status === 'processing') throw new Error('Die Übersicht wird vorbereitet. Bitte gleich erneut versuchen.')
      const data = normalizeMatches(result, qc.getQueryData<MatchListData>(key))
      if (data.status === 'unavailable' || data.status === 'failed') {
        throw new Error('Spieldaten sind derzeit nicht verfügbar.')
      }
      return { competition, data }
    },
    onSuccess: ({ competition: refreshedCompetition, data }) => {
      if (refreshedCompetition === 'wc2026') qc.setQueryData(['matches', refreshedCompetition], data)
      else {
        qc.setQueryData(['matches', refreshedCompetition, 'overview'], data)
        qc.invalidateQueries({ queryKey: ['matches', refreshedCompetition], exact: true })
      }
      qc.invalidateQueries({ queryKey: ['matches', refreshedCompetition, 'core'] })
      qc.invalidateQueries({ queryKey: ['matches', refreshedCompetition, 'analysis'] })
      qc.invalidateQueries({ queryKey: ['archive', refreshedCompetition] })
      qc.invalidateQueries({ queryKey: ['quota', refreshedCompetition] })
      qc.invalidateQueries({ queryKey: ['dataStatus', refreshedCompetition] })
      qc.invalidateQueries({ queryKey: ['modelEvaluation', refreshedCompetition] })
    },
  })
}
