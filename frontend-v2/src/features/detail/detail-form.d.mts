export interface TipCountRow {
  tip: string
  count: string
}

export function parseScoreFields(value: unknown): { home: string; away: string } | null
export function formatScoreFields(home: string, away: string): string | null
export function parseTipCountRows(rows: TipCountRow[]): Record<string, number> | null
export function formatDataStatus(status?: string | null, observedAt?: string | null, now?: number): string
export function formatObservedAt(value?: string | null, now?: number): string
