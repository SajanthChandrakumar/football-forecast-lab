export declare const FALLBACK_COMPETITIONS: readonly {
  id: string
  short_name: string
  display_name: string
}[]
export declare const COMPETITIONS: readonly ['wc2026', 'ucl2026', 'epl2026']
export type CompetitionId = string
export declare function validCompetition(value: unknown, registered?: readonly string[]): CompetitionId
export declare function competitionPath(path: string, competition: CompetitionId): string
export declare function competitionLabel(competition: CompetitionId, competitions?: { id: string; short_name?: string }[]): string
