import type { MatchIntelligence, MatchLineup } from './types'

export type LineupState =
  | { kind: 'confirmed'; home: MatchLineup; away: MatchLineup; observedAt?: string | null; source?: string }
  | { kind: 'unavailable'; partial?: boolean; message: string }

export function lineupState(data: MatchIntelligence | undefined, homeTeam: string, awayTeam: string): LineupState
