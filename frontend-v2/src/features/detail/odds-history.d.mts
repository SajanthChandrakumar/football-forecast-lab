type OddsHistoryObservation = { observed_at: string; probabilities: { home: number; draw: number; away: number }; [key: string]: unknown }
export function chronologicalOddsHistory<T extends OddsHistoryObservation>(observations?: T[]): T[]
export function oddsHistoryChartRows(observations?: OddsHistoryObservation[]): { observedTimestamp: number; Heim: number; Remis: number; Auswärts: number }[]
