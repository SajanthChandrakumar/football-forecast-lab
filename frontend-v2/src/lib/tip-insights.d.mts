import type { PlayerForm, PlayerFormEntry, TeamForm, XpTip } from './types'

export interface TipInsight {
  tip: string
  expectedPoints: number
  exactChance: number | null
}

export function rankedTipInsights(
  tips?: XpTip[],
  matrix?: Record<number, Record<number, number>>,
  limit?: number,
): TipInsight[]

export function scoreProbabilitySummary(
  matrix?: Record<number, Record<number, number>>,
  modelTip?: string | null,
): { topScores: { tip: string; chance: number }[]; modelTipChance: number | null } | null

export function recentFormSummary(form?: TeamForm): string
export function teamHistoryAnalysis(form?: TeamForm): string | null
export function teamHistoryMetrics(form?: TeamForm): {
  matches: number
  goalsFor: number
  goalsAgainst: number
  averageFor: number
  averageAgainst: number
  cleanSheets: number
  bothTeamsScored: number
} | null
export function matchFormInsights(homeName: string, homeForm: TeamForm | undefined, awayName: string, awayForm: TeamForm | undefined): {
  kind: 'form' | 'goals'
  title: string
  detail: string
}[]
export function playerFormSummary(player: PlayerFormEntry): string
export function playerFormStatusMessage(playerForm?: PlayerForm): string
export function matchLoadSummary(form?: TeamForm, kickoff?: string): string | null
