import type { CompetitionId, EloHistory, EloRatingsStatus, Match, StandingsRow, TeamForm, TeamFormMatch } from './types'

export interface TeamFormEntry {
  /** Official standings name shown in the UI. */
  team: string
  /** Elo API key used to read ratings, history, and match details. */
  ratingKey: string
}

export interface TeamFormCoverage {
  complete: boolean
  standingsValid: boolean
  required: number
  available: number
  missing: string[]
}

export interface TeamFormSnapshotState extends TeamFormCoverage {
  status: EloRatingsStatus['status'] | null
  showRatings: boolean
  showAlert: boolean
  snapshotAvailable: number
  snapshotRequired: number
  snapshotMissing: string[]
  error: string | null
}

export declare function teamFormCanonicalName(team: string): string
export declare function teamFormCoverage(competition: CompetitionId, teams: string[], standingsRows?: StandingsRow[]): TeamFormCoverage
export declare function teamFormSnapshotState(ratingCoverage: TeamFormCoverage, snapshotStatus?: EloRatingsStatus | null): TeamFormSnapshotState
export declare function teamFormEntries(competition: CompetitionId, teams: string[], standingsRows?: StandingsRow[]): TeamFormEntry[]
export declare function teamFormTeamNames(competition: CompetitionId, teams: string[], standingsRows?: StandingsRow[]): string[]
export declare function teamsWithoutHistory(teams: string[], history?: EloHistory): string[]
export declare function verifiedClubFormMatches(form: TeamForm | null | undefined, options?: { before?: string | null; competition?: 'all' | 'league' | 'cup' | 'europe' }): TeamFormMatch[]
export declare function clubFormSummary(matches: TeamFormMatch[]): { played: number; wins: number; draws: number; losses: number; goalsFor: number; goalsAgainst: number }
export declare function clubFormHomeAwayScore(match: TeamFormMatch): string | null
export declare function clubFormForTeam(team: string, fixtures?: Match[]): TeamForm | null
export declare function chronologicalRecentMatches<T extends { playedAt?: string | null }>(matches: T[], limit?: number): T[]
export declare function formatEloTimestamp(timestamp: number): string
