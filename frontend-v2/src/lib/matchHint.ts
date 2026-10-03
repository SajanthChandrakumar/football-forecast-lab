import type { Match, Probabilities } from './types.ts'
import { computeImpliedProbs } from './util.ts'

export type MatchHintConfidence = 'high' | 'medium' | 'low' | 'unavailable'
export type MatchHintSource = 'bookmaker' | 'elo' | 'unavailable'

export interface MatchHint {
  available: boolean
  summary: string
  confidence: MatchHintConfidence
  confidenceLabel: 'Hoch' | 'Mittel' | 'Niedrig' | 'Nicht verfügbar'
  source: MatchHintSource
  sourceLabel: 'Buchmacherquote' | 'Elo-Modellquote · nicht wettbar' | 'Nicht verfügbar'
  probabilities: Probabilities | null
  observedAt: string | null
  reasons: string[]
}

type Outcome = 'home' | 'draw' | 'away'

const UNAVAILABLE_HINT: MatchHint = {
  available: false,
  summary: 'Für eine verständliche Erklärung fehlen derzeit ausreichende Daten.',
  confidence: 'unavailable',
  confidenceLabel: 'Nicht verfügbar',
  source: 'unavailable',
  sourceLabel: 'Nicht verfügbar',
  probabilities: null,
  observedAt: null,
  reasons: [],
}

const isFiniteNumber = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value)

function displayName(team: string, display?: string): string {
  return display?.replace(/^\p{RI}\p{RI}\s*/u, '') || team
}

function normalized(probabilities?: Probabilities | null): Probabilities | null {
  if (!probabilities) return null
  const values = [probabilities.home, probabilities.draw, probabilities.away]
  if (!values.every((value) => isFiniteNumber(value) && value >= 0)) return null
  const total = values.reduce((sum, value) => sum + value, 0)
  if (total <= 0) return null
  return {
    home: probabilities.home / total,
    draw: probabilities.draw / total,
    away: probabilities.away / total,
  }
}

function selectedProbabilities(match: Match): {
  probabilities: Probabilities
  source: MatchHintSource
  sourceLabel: MatchHint['sourceLabel']
  observedAt: string | null
} | null {
  const odds = match.odds
  if (odds && [odds.home, odds.draw, odds.away].every((value) => isFiniteNumber(value) && value > 1)) {
    return {
      probabilities: computeImpliedProbs(odds),
      source: 'bookmaker',
      sourceLabel: 'Buchmacherquote',
      observedAt: match.odds_observed_at ?? null,
    }
  }

  const probabilities = match.source_mode === 'elo-only' ? normalized(match.probabilities) : null
  if (!probabilities) return null
  return {
    probabilities,
    source: 'elo',
    sourceLabel: 'Elo-Modellquote · nicht wettbar',
    observedAt: match.observed_at ?? null,
  }
}

function missingCount(match: Match, outcome: 'home' | 'away'): number {
  const rawName = outcome === 'home' ? match.home_team : match.away_team
  const shownName = outcome === 'home'
    ? displayName(match.home_team, match.home_disp)
    : displayName(match.away_team, match.away_disp)
  return match.lineup_diff?.[rawName]?.missing?.length
    ?? match.lineup_diff?.[shownName]?.missing?.length
    ?? 0
}

function reasonCandidates(match: Match, favorite: Outcome, homeName: string, awayName: string): string[] {
  const reasons: string[] = []
  if (favorite !== 'draw') {
    const homeXg = match.xg_home
    const awayXg = match.xg_away
    if (
      isFiniteNumber(homeXg)
      && isFiniteNumber(awayXg)
      && Math.abs(homeXg - awayXg) >= 0.35
      && ((favorite === 'home' && homeXg > awayXg) || (favorite === 'away' && awayXg > homeXg))
    ) {
      reasons.push(`Torerwartung: ${homeName} ${homeXg.toFixed(2)} zu ${awayName} ${awayXg.toFixed(2)}.`)
    }

    const favoriteForm = favorite === 'home' ? match.home_form : match.away_form
    const opponentForm = favorite === 'home' ? match.away_form : match.home_form
    if (favoriteForm?.on_fire && !opponentForm?.on_fire) {
      reasons.push(`${favorite === 'home' ? homeName : awayName} kommt mit der stärkeren aktuellen Form.`)
    }

    const homeShare = match.elo_home_share
    if (
      isFiniteNumber(homeShare)
      && Math.abs(homeShare - 0.5) >= 0.1
      && ((favorite === 'home' && homeShare > 0.5) || (favorite === 'away' && homeShare < 0.5))
    ) {
      const favoriteShare = favorite === 'home' ? homeShare : 1 - homeShare
      reasons.push(`Club-Elo sieht ${favorite === 'home' ? homeName : awayName} bei ${Math.round(favoriteShare * 100)} % im direkten Stärkevergleich.`)
    }

    const favoriteMissing = missingCount(match, favorite)
    const opponentMissing = missingCount(match, favorite === 'home' ? 'away' : 'home')
    if (opponentMissing - favoriteMissing >= 2) {
      reasons.push('Beim Gegner sind mehr fehlende Spieler gemeldet.')
    }
  }

  if (match.is_ko_phase && match.first_leg_score) {
    reasons.push('Das Hinspielergebnis kann den Spielverlauf stärker beeinflussen.')
  }
  return reasons
}

export function buildMatchHint(match: Match): MatchHint {
  const selected = selectedProbabilities(match)
  if (!selected) return { ...UNAVAILABLE_HINT, reasons: [] }

  const outcomes: { outcome: Outcome; probability: number }[] = [
    { outcome: 'home', probability: selected.probabilities.home },
    { outcome: 'draw', probability: selected.probabilities.draw },
    { outcome: 'away', probability: selected.probabilities.away },
  ]
  outcomes.sort((a, b) => b.probability - a.probability)
  const favorite = outcomes[0].outcome
  const top = outcomes[0].probability
  const gap = top - outcomes[1].probability
  const confidence: Exclude<MatchHintConfidence, 'unavailable'> = top >= 0.55 && gap >= 0.15
    ? 'high'
    : top >= 0.43 && gap >= 0.08
      ? 'medium'
      : 'low'
  const confidenceLabel = confidence === 'high' ? 'Hoch' : confidence === 'medium' ? 'Mittel' : 'Niedrig'

  const homeName = displayName(match.home_team, match.home_disp)
  const awayName = displayName(match.away_team, match.away_disp)
  const lead = favorite === 'draw'
    ? 'Die höchste Einzelwahrscheinlichkeit liegt beim Unentschieden.'
    : `Die höchste Einzelwahrscheinlichkeit entfällt auf ${favorite === 'home' ? homeName : awayName}.`
  const reasons = reasonCandidates(match, favorite, homeName, awayName).slice(0, 2)

  return {
    available: true,
    summary: lead,
    confidence,
    confidenceLabel,
    source: selected.source,
    sourceLabel: selected.sourceLabel,
    probabilities: selected.probabilities,
    observedAt: selected.observedAt,
    reasons,
  }
}
