import type { Match } from './types'

export interface FixtureRound {
  key: string
  label: string
  matches: Match[]
  firstKickoff: number
  lastKickoff: number
}

export declare function groupFixturesByRound(matches: Match[]): FixtureRound[]

export interface FixtureDay {
  key: string
  relativeLabel: 'Heute' | 'Morgen' | null
  dateLabel: string
  matches: Match[]
}

export declare function groupFixturesByDay(matches: Match[], now?: number): FixtureDay[]
