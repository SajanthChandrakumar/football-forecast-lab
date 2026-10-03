import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useArchive, useCustomBot, useSimulateBot } from '../../hooks/queries'
import { useAppState } from '../../state/AppState'
import { api } from '../../lib/api'
import { commonPerformance, officialPerformance } from '../../lib/performance.mjs'
import type { Archive, ArchiveEntry, BotKey } from '../../lib/types'

export const HOUSE_BOTS: { key: BotKey; label: string; color: string }[] = [
  { key: 'broker', label: 'Broker', color: 'var(--blue)' },
  { key: 'professor', label: 'Professor', color: 'var(--text-2)' },
  { key: 'sniper', label: 'X-Sniper', color: 'var(--purple)' },
  { key: 'gambler', label: 'Zocker', color: 'var(--amber)' },
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
  algoTotal: number
  algoTendency: number
  algoCount: number
  reconstructedCount: number
  reconstructedPoints: number
  reconstructedTendency: number
  hasReconstructed: boolean
}

export interface CommonPerformance {
  matches: number
  userPoints: number
  userTendency: number
  algoPoints: number
  algoTendency: number
  matchIds: string[]
}

function entryDate(e: ArchiveEntry): string {
  return e.metadata?.commence_time ?? e.pre_match_snapshot?.timestamp_recorded ?? ''
}

export function aggregate(archive: Archive | undefined) {
  const completed: CompletedMatch[] = []
  const totals: PerformanceTotals = {
    completed: 0, userCount: 0, totalPoints: 0, correctTendency: 0,
    algoTotal: 0, algoTendency: 0, algoCount: 0, reconstructedCount: 0,
    reconstructedPoints: 0, reconstructedTendency: 0,
    hasReconstructed: false,
  }
  const official = officialPerformance(archive, HOUSE_BOTS.map(({ key }) => key))
  const comparison = commonPerformance(archive) as CommonPerformance
  const botStats = official.botStats as Record<BotKey, { pts: number; tipped: number; tendency: number }>
  totals.algoTotal = official.algoTotal
  totals.algoCount = official.algoCount
  totals.algoTendency = official.algoTendency
  totals.reconstructedCount = official.reconstructedCount
  totals.reconstructedPoints = official.reconstructedPoints
  totals.reconstructedTendency = official.reconstructedTendency
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
  return { completed, totals, botStats, comparison }
}

export function usePerformanceData() {
  const { competition } = useAppState()
  const archiveQuery = useArchive()
  const { data: archive, isLoading, isError, refetch } = archiveQuery
  const { data: customBot } = useCustomBot()
  const simulate = useSimulateBot()

  const { completed, totals, botStats, comparison } = useMemo(() => aggregate(archive), [archive])

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
        color: 'var(--blue)',
        pts: customSim.total_points,
        tipped: customSim.matches,
        tendency: Math.round((customSim.tendency_rate ?? 0) * customSim.matches),
        isExtra: true,
        pointsByMatch: Object.fromEntries(customSim.breakdown.map((b) => [b.match_id, b.points])),
      })
    }
    return out
  }, [customBot, customSim])

  return {
    archive, completed, totals, botStats, comparison, extraBots, customBot, simulate,
    isLoading, isError, retryArchive: () => refetch(),
  }
}
