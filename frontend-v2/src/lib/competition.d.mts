export declare const COMPETITIONS: readonly ['wc2026', 'ucl2026']
export type CompetitionId = (typeof COMPETITIONS)[number]
export declare function validCompetition(value: unknown): CompetitionId
export declare function competitionPath(path: string, competition: CompetitionId): string
export declare function competitionLabel(competition: CompetitionId, competitions?: { id: string; short_name?: string }[]): string
