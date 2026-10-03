import type { Archive, ArchiveEntry, BotKey } from './types'

export interface PerformanceBotStat {
  pts: number
  tipped: number
  tendency: number
}

export declare function isOfficialPerformanceEntry(entry: ArchiveEntry): boolean

export declare function commonPerformance(archive: Archive | undefined): {
  matches: number
  userPoints: number
  userTendency: number
  algoPoints: number
  algoTendency: number
  matchIds: string[]
}

export declare function officialPerformance(archive: Archive | undefined, botKeys: BotKey[]): {
  algoTotal: number
  algoCount: number
  algoTendency: number
  reconstructedCount: number
  reconstructedPoints: number
  reconstructedTendency: number
  botStats: Record<BotKey, PerformanceBotStat>
}
