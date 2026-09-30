import type { Archive } from './types'

export interface LocalRetrospectiveTip {
  user_tip: string
  points: number
  actual_score: string
  saved_at: string
}

export interface RetrospectiveImportResult {
  imported: number
  points: number
  errors: string[]
}

export declare function readRetrospectiveTips(
  competition: string,
  storage?: Pick<Storage, 'getItem'>,
): Record<string, LocalRetrospectiveTip>

export declare function importRetrospectiveTips(
  competition: string,
  rows: unknown,
  archive: Archive | undefined,
  storage?: Pick<Storage, 'getItem' | 'setItem'>,
): RetrospectiveImportResult

export declare function applyRetrospectiveTips(
  archive: Archive | undefined,
  localTips: Record<string, LocalRetrospectiveTip>,
): Archive
