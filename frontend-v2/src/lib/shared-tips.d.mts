import type { Archive, Match } from './types'

export declare function getSavedTipForMatch(match: Match, archive: Archive | undefined): string
export declare function openUnsubmittedTips(matches: Match[], archive: Archive | undefined, now?: number): Match[]
