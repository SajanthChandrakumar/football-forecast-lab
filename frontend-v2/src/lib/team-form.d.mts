import type { CompetitionId, EloHistory, EloRatingsStatus, StandingsRow } from './types'

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
