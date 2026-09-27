import type { TeamForm, XpTip } from './types'

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

export function recentFormSummary(form?: TeamForm): string
