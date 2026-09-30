import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useArchive, useCustomBot, useSimulateBot } from '../../hooks/queries'
import { useAppState } from '../../state/AppState'
import { api } from '../../lib/api'
import { officialPerformance } from '../../lib/performance.mjs'
import { applyRetrospectiveTips, importRetrospectiveTips as savePrivateTips, readRetrospectiveTips } from '../../lib/retrospective-tips.mjs'
import type { Archive, ArchiveEntry, BotKey } from '../../lib/types'

export const HOUSE_BOTS: { key: BotKey; label: string; color: string }[] = [
  { key: 'broker', label: 'Broker', color: '#5b9bd5' },
  { key: 'professor', label: 'Professor', color: '#4caf82' },
  { key: 'sniper', label: 'X-Sniper', color: '#9b6dd1' },
  { key: 'gambler', label: 'Zocker', color: '#9a9a9a' },
]

export interface CompletedMatch {
  id: string
  entry: ArchiveEntry
  points: number
  sortDate: string
}

export interface ScoreRow {
  key: string
  label: string
  color: string
  pts: number
  tipped: number
  tendency: number
  isUser?: boolean
  isExtra?: boolean
  pointsByMatch?: Record<string, number>
}

export interface PerformanceTotals {
  completed: number
  userCount: number
  totalPoints: number
  correctTendency: number
  algoAllTotal: number
  algoAllCount: number
  algoAllTendency: number
  algoTotal: number
  algoTendency: number
  algoCount: number
  legacyCount: number
  legacyPoints: number
  legacyTendency: number
  reconstructedCount: number
  reconstructedPoints: number
  reconstructedTendency: number
  probabilityCount: number
  brierScore: number | null
  hasLegacy: boolean
  hasReconstructed: boolean
}

function entryDate(e: ArchiveEntry): string {
  return e.metadata?.commence_time ?? e.pre_match_snapshot?.timestamp_recorded ?? ''
}

export function aggregate(archive: Archive | undefined) {
  const completed: CompletedMatch[] = []
  const totals: PerformanceTotals = {
    completed: 0, userCount: 0, totalPoints: 0, correctTendency: 0,
    algoAllTotal: 0, algoAllCount: 0, algoAllTendency: 0,
    algoTotal: 0, algoTendency: 0, algoCount: 0, legacyCount: 0,
    legacyPoints: 0, legacyTendency: 0, reconstructedCount: 0,
    reconstructedPoints: 0, reconstructedTendency: 0, probabilityCount: 0,
    brierScore: null, hasLegacy: false,
    hasReconstructed: false,
  }
  const official = officialPerformance(archive, HOUSE_BOTS.map(({ key }) => key))
  const botStats = official.botStats as Record<BotKey, { pts: number; tipped: number; tendency: number }>
  totals.algoAllTotal = official.algoAllTotal
  totals.algoAllCount = official.algoAllCount
  totals.algoAllTendency = official.algoAllTendency
  totals.algoTotal = official.algoTotal
  totals.algoCount = official.algoCount
  totals.algoTendency = official.algoTendency
  totals.legacyCount = official.legacyCount
  totals.legacyPoints = official.legacyPoints
  totals.legacyTendency = official.legacyTendency
  totals.reconstructedCount = official.reconstructedCount
  totals.reconstructedPoints = official.reconstructedPoints
  totals.reconstructedTendency = official.reconstructedTendency
  totals.probabilityCount = official.probabilityCount
  totals.brierScore = official.brierScore
  totals.hasLegacy = official.legacyCount > 0
  totals.hasReconstructed = official.reconstructedCount > 0

  for (const [id, entry] of Object.entries(archive ?? {})) {
    if (entry.post_match_result?.status !== 'completed') continue
    const pts = entry.post_match_result.points_earned ?? 0
    totals.completed++
    if (entry.prediction?.user_tip != null) {
      totals.userCount++
      totals.totalPoints += pts
      if (pts >= 5) totals.correctTendency++
    }

    completed.push({ id, entry, points: pts, sortDate: entryDate(entry) })
  }

  completed.sort((a, b) => b.sortDate.localeCompare(a.sortDate)) // newest first
  return { completed, totals, botStats }
}

export function usePerformanceData() {
  const { competition } = useAppState()
  const { data: archive, isLoading } = useArchive()
  const { data: customBot } = useCustomBot()
  const simulate = useSimulateBot()
  const [localTipState, setLocalTipState] = useState(() => ({
    competition,
    tips: readRetrospectiveTips(competition),
  }))
  useEffect(() => {
    setLocalTipState({ competition, tips: readRetrospectiveTips(competition) })
  }, [competition])
  const localTips = useMemo(
    () => localTipState.competition === competition ? localTipState.tips : {},
    [localTipState, competition],
  )
  const privateArchive = useMemo(() => applyRetrospectiveTips(archive, localTips), [archive, localTips])

  const { completed, totals, botStats } = useMemo(() => aggregate(privateArchive), [privateArchive])

  const importPrivateTips = (rows: unknown) => {
    const result = savePrivateTips(competition, rows, archive)
    setLocalTipState({ competition, tips: readRetrospectiveTips(competition) })
    return result
  }
  const privateTipCount = Object.keys(localTips).length
  const privateTipPoints = Object.values(localTips).reduce((sum, tip) => sum + tip.points, 0)

  // Saved build-a-bot competes alongside the house bots — replayed via simulate.
  const { data: customSim } = useQuery({
    queryKey: ['customBotSim', competition, customBot?.params],
    queryFn: () => api.simulateBot(competition, customBot!.params!),
    enabled: Boolean(customBot?.exists && customBot.params),
    staleTime: 300_000,
  })

  const extraBots = useMemo<ScoreRow[]>(() => {
    const out: ScoreRow[] = []
    if (customBot?.exists && customSim) {
      out.push({
        key: 'custom',
        label: customBot.name ?? 'Mein Bot',
        color: '#2dd4bf',
        pts: customSim.total_points,
        tipped: customSim.matches,
        tendency: Math.round((customSim.tendency_rate ?? 0) * customSim.matches),
        isExtra: true,
        pointsByMatch: Object.fromEntries(customSim.breakdown.map((b) => [b.match_id, b.points])),
      })
    }
    return out
  }, [customBot, customSim])

  return { archive, completed, totals, botStats, extraBots, customBot, simulate, isLoading, importPrivateTips, privateTipCount, privateTipPoints }
}
