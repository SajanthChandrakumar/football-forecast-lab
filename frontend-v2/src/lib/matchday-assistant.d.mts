import type { Archive, Match } from './types'

export const TIP_BATCH_LIMIT: number
export const TIP_SAVE_CONCURRENCY: number
export function normalizeScoreTip(value: unknown): string | null
export function isValidScoreTip(value: unknown): boolean
export interface AssistantRow {
  match: Match
  status: 'upcoming' | 'pending' | 'played' | 'unscheduled'
  kickoff: number
  savedTip: string
  suggestion: string
  sourceLabel: string
  stale: boolean
  observedAt: string
  value: string
  editable: boolean
  saved: boolean
  changed: boolean
  touched: boolean
}
export function buildAssistantRows(
  matches: Match[],
  archive: Archive | undefined,
  drafts: Record<string, string>,
  savedOverrides: Record<string, string>,
  now?: number,
): AssistantRow[]
export function getSaveCandidates(rows: AssistantRow[]): { match: Match; tip: string }[]
export function saveTipBatch<T>(
  items: T[],
  save: (item: T) => Promise<unknown>,
): Promise<{ results: { item: T; ok: true }[] | { item: T; ok: false; error: string }[]; remaining: number }>
