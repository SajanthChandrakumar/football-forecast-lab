import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useAppState } from '../state/AppState'
import type { CustomBotParams, Match, MatchesResponse, PoolContext, RawMatch, UnavailablePayload } from '../lib/types'

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

type MatchListData = { matches: Match[] } & Partial<Pick<UnavailablePayload, 'status' | 'source' | 'observed_at' | 'error'>>

function normalizeMatches(result: MatchesResponse): MatchListData {
  return Array.isArray(result)
    ? { matches: result }
    : { ...result, matches: result.data ?? [] }
}

export const useMatches = () => {
  const { competition } = useAppState()
  const query = useQuery({
    queryKey: ['matches', competition],
    queryFn: async () => normalizeMatches(await api.matches(competition)),
    staleTime: 60_000,
    select: (result) => ({ ...result, matches: dedupeMatches(result.matches) }),
  })
  return { ...query, data: query.data?.matches, availability: query.data }
}

export const useArchive = () => {
  const { competition } = useAppState()
  return useQuery({ queryKey: ['archive', competition], queryFn: () => api.archive(competition), staleTime: 60_000 })
}

export const useModelEvaluation = () => {
  const { competition } = useAppState()
  return useQuery({ queryKey: ['modelEvaluation', competition], queryFn: () => api.modelEvaluation(competition), staleTime: 60_000 })
}

export const useStandings = () => {
  const { competition } = useAppState()
  return useQuery({ queryKey: ['standings', competition], queryFn: () => api.standings(competition), staleTime: 60_000 })
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
    enabled: competition === 'ucl2026',
    staleTime: 300_000,
  })
}

export const useKnockoutSimulation = () => {
  const { competition } = useAppState()
  return useQuery({
    queryKey: ['knockoutSim', competition],
    queryFn: () => competition === 'ucl2026' ? api.simulateUcl(competition) : api.simulateKnockout(competition),
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
    mutationFn: ({ match }: { match: RawMatch }) => api.predict(match, competition),
  })
}

export const useSaveUserTip = () => {
  const { competition } = useAppState()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ matchId, tip, targetCompetition }: { matchId: string; tip: string; targetCompetition?: typeof competition }) =>
      api.saveUserTip(targetCompetition ?? competition, matchId, tip),
    onSuccess: (_, { targetCompetition }) => {
      const savedCompetition = targetCompetition ?? competition
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
    mutationFn: async () => normalizeMatches(await api.matches(competition, true)),
    onSuccess: (data) => {
      qc.setQueryData(['matches', competition], data)
      qc.invalidateQueries({ queryKey: ['archive', competition] })
      qc.invalidateQueries({ queryKey: ['quota', competition] })
      qc.invalidateQueries({ queryKey: ['modelEvaluation', competition] })
    },
  })
}
