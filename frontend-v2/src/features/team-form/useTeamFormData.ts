import { useMemo } from 'react'
import { useArchive, useEloHistory, useEloRatings, useEloRatingsStatus, useStandings } from '../../hooks/queries'
import { useAppState } from '../../state/AppState'
import { normTeam } from '../../lib/util'
import { teamFormCanonicalName, teamFormCoverage, teamFormEntries, teamFormSnapshotState } from '../../lib/team-form.mjs'
import type { Archive } from '../../lib/types'

export interface TeamRow {
  team: string
  elo: number
  delta: number | null
  w: number; d: number; l: number
  last5: ('W' | 'D' | 'L')[]
}

export interface MatchInfo {
  opponent: string
  score: string
  result: 'W' | 'D' | 'L'
}

/** Per-team match log keyed by match_id — feeds the Elo chart tooltip. */
function buildMatchInfo(archive: Archive | undefined): Record<string, Record<string, MatchInfo>> {
  const out: Record<string, Record<string, MatchInfo>> = {}
  for (const [matchId, m] of Object.entries(archive ?? {})) {
    const pmr = m.post_match_result
    if (pmr?.status !== 'completed' || !pmr.actual_score) continue
    const [hs, as] = pmr.actual_score.split(':').map(Number)
    if (Number.isNaN(hs) || Number.isNaN(as)) continue
    const home = teamFormCanonicalName(normTeam(m.metadata.home_team))
    const away = teamFormCanonicalName(normTeam(m.metadata.away_team))
    ;(out[home] ??= {})[matchId] = {
      opponent: away, score: `${hs}:${as}`,
      result: hs > as ? 'W' : hs < as ? 'L' : 'D',
    }
    ;(out[away] ??= {})[matchId] = {
      opponent: home, score: `${as}:${hs}`,
      result: as > hs ? 'W' : as < hs ? 'L' : 'D',
    }
  }
  return out
}

export function useTeamFormData() {
  const { competition } = useAppState()
  const { data: history, isLoading: l1 } = useEloHistory()
  const { data: ratings, isLoading: l2 } = useEloRatings()
  const { data: eloStatus, isLoading: l5, error: eloStatusError } = useEloRatingsStatus()
  const { data: archive, isLoading: l3 } = useArchive()
  const { data: standingsData, isLoading: l4 } = useStandings()

  const standingsRows = useMemo(() => standingsData?.flatMap((group) => group.rows ?? []) ?? [], [standingsData])
  const allTeams = useMemo(() => new Set<string>([
    ...Object.keys(ratings ?? {}),
    ...Object.keys(history ?? {}),
  ]), [ratings, history])
  const ratingTeams = useMemo(() => Object.keys(ratings ?? {}), [ratings])
  const availableTeams = useMemo(
    () => competition === 'ucl2026' ? ratingTeams : [...allTeams],
    [competition, ratingTeams, allTeams],
  )
  const entries = useMemo(
    () => teamFormEntries(competition, availableTeams, standingsRows),
    [competition, availableTeams, standingsRows],
  )
  const coverage = useMemo(
    () => teamFormSnapshotState(
      teamFormCoverage(competition, availableTeams, standingsRows),
      eloStatus ?? (eloStatusError
        ? { status: 'unavailable', source: 'clubelo', error: eloStatusError instanceof Error ? eloStatusError.message : 'Elo status unavailable' }
        : null),
    ),
    [competition, availableTeams, standingsRows, eloStatus, eloStatusError],
  )
  const canonicalMatchInfo = useMemo(() => buildMatchInfo(archive), [archive])
  const chartHistory = useMemo(() => {
    const result = { ...(history ?? {}) }
    for (const { team, ratingKey } of entries) {
      if (history?.[ratingKey]) result[team] = history[ratingKey]
    }
    return result
  }, [history, entries])
  const matchInfo = useMemo(() => {
    const result = { ...canonicalMatchInfo }
    for (const { team, ratingKey } of entries) {
      result[team] = canonicalMatchInfo[ratingKey] ?? {}
    }
    return result
  }, [canonicalMatchInfo, entries])

  const rows = useMemo<TeamRow[]>(() => {
    const out: TeamRow[] = []
    for (const { team, ratingKey } of entries) {
      const hist = history?.[ratingKey] ?? []
      const baseline = hist[0]?.elo
      const current = ratings?.[ratingKey]?.elo ?? hist[hist.length - 1]?.elo
      if (current == null) continue
      const log = Object.values(canonicalMatchInfo[ratingKey] ?? {})
      const w = log.filter((x) => x.result === 'W').length
      const d = log.filter((x) => x.result === 'D').length
      const l = log.filter((x) => x.result === 'L').length
      out.push({
        team,
        elo: current,
        delta: baseline != null ? current - baseline : null,
        w, d, l,
        last5: log.slice(-5).map((x) => x.result),
      })
    }
    return out.sort((a, b) => b.elo - a.elo)
  }, [ratings, history, entries, canonicalMatchInfo])

  return { rows, history: chartHistory, matchInfo, coverage, isLoading: l1 || l2 || l3 || (competition === 'ucl2026' && (l4 || l5)) }
}
