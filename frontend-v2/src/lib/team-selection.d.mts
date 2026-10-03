export declare function sanitizeTeamSelection(teams: unknown): string[]
export declare function readTeamSelection(competition: string, storage?: Storage): string[] | null
export declare function writeTeamSelection(competition: string, teams: unknown, storage?: Storage): string[]
export declare function resolveInitialTeamSelection(
  savedSelection: unknown,
  matches: Array<{ home_team?: string; away_team?: string; completed?: boolean; actual_score?: string | null; raw_match?: { commence_time?: string | null } }>,
  rows: Array<{ team: string }>,
  now?: number,
): string[]
