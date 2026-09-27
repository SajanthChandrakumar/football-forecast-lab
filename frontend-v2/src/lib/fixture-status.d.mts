import type { Match } from './types'

export type FixtureStatus = 'upcoming' | 'pending' | 'played' | 'unscheduled'
export declare function fixtureStatus(match: Match, now?: number): FixtureStatus
export declare function preferredFixtureTab(counts: Record<FixtureStatus, number>): FixtureStatus
export declare function sharedTipIsOpen(commenceTime?: string | null, now?: number): boolean
