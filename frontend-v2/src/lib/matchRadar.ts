import { buildMatchHint, type MatchHint } from './matchHint.ts'
import type { Match } from './types.ts'

export type RadarCategory = 'safe' | 'open' | 'surprise'

export interface RadarMatch {
  match: Match
  category: RadarCategory
  hint: MatchHint
  reason: string
}

export interface MatchdayRadar {
  matches: RadarMatch[]
  counts: Record<RadarCategory, number>
  tipCard: string
}

const MATCHDAY_WINDOW_MS = 72 * 60 * 60 * 1000
const SURPRISE_EDGE = 0.1

function displayName(team: string, display?: string): string {
  return display?.replace(/^\p{RI}\p{RI}\s*/u, '') || team
}

function classify(match: Match): RadarMatch {
  const hint = buildMatchHint(match)
  const edge = match.edge_home
  const hasComparison = match.odds
    && Number.isFinite(match.elo_home_share)
    && Number.isFinite(match.market_home_share)
    && typeof edge === 'number'
    && Number.isFinite(edge)

  if (hasComparison && Math.abs(edge) >= SURPRISE_EDGE) {
    const team = edge > 0
      ? displayName(match.home_team, match.home_disp)
      : displayName(match.away_team, match.away_disp)
    return { match, hint, category: 'surprise', reason: `${team} wird vom Modell stärker eingeschätzt als vom Markt.` }
  }

  if (hint.confidence === 'high') {
    return { match, hint, category: 'safe', reason: hint.summary }
  }

  const reason = hint.available
    ? 'Das Spiel ist offen – den Tipp vor Anstoß noch einmal prüfen.'
    : 'Noch nicht genug Daten für einen klaren Tipp.'
  return { match, hint, category: 'open', reason }
}

export function buildMatchdayRadar(matches: Match[], now = Date.now()): MatchdayRadar {
  const upcoming = matches
    .filter((match) => !match.completed && !match.actual_score)
    .map((match) => ({ match, time: Date.parse(String(match.raw_match?.commence_time ?? '')) }))
    .filter(({ time }) => Number.isFinite(time) && time > now)
    .sort((a, b) => a.time - b.time)

  const firstKickoff = upcoming[0]?.time
  const selected = firstKickoff === undefined
    ? []
    : upcoming.filter(({ time }) => time - firstKickoff <= MATCHDAY_WINDOW_MS).map(({ match }) => classify(match))

  const counts = { safe: 0, open: 0, surprise: 0 }
  for (const item of selected) counts[item.category] += 1

  const tipCard = [
    'Spieltag-Radar',
    ...selected.map(({ match }) => {
      const home = displayName(match.home_team, match.home_disp)
      const away = displayName(match.away_team, match.away_disp)
      const tip = match.top_tip && match.top_tip !== 'N/A' ? match.top_tip : '–'
      return `${home} – ${away}: ${tip}`
    }),
  ].join('\n')

  return { matches: selected, counts, tipCard }
}
