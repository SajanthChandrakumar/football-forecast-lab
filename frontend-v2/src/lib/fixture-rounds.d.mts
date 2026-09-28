import type { Match } from './types'

export interface FixtureRound {
  key: string
  label: string
  matches: Match[]
  firstKickoff: number
  lastKickoff: number
}

export declare function groupFixturesByRound(matches: Match[]): FixtureRound[]
