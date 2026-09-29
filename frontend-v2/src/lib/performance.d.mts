import type { Archive, ArchiveEntry, BotKey } from './types'

export interface PerformanceBotStat {
  pts: number
  tipped: number
  tendency: number
}

export declare function isOfficialPerformanceEntry(entry: ArchiveEntry): boolean
export declare function performanceEntryKind(entry: ArchiveEntry): 'pending' | 'verified' | 'legacy' | 'reconstructed'

export declare function officialPerformance(archive: Archive | undefined, botKeys: BotKey[]): {
  algoTotal: number
  algoCount: number
  algoTendency: number
  legacyCount: number
  legacyPoints: number
  legacyTendency: number
  reconstructedCount: number
  reconstructedPoints: number
  reconstructedTendency: number
  probabilityCount: number
  brierScore: number | null
  botStats: Record<BotKey, PerformanceBotStat>
}
