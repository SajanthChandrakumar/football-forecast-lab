import type { Match, Prediction } from './types'
import { lineupState } from './match-intelligence.mjs'

export type DataStatus = 'fresh' | 'stale' | 'partial' | 'unavailable' | 'unknown' | 'failed'
export interface MatchDataRow {
  key: string
  label: string
  status: DataStatus
  source: string
  observedAt: string | null
  message: string
}
export interface MatchDataStatus {
  status: DataStatus
  title: string
  explanation: string
  rows: MatchDataRow[]
}

const sourceLabels: Record<string, string> = {
  odds_api: 'The Odds API', api_football: 'API-Football', clubelo: 'ClubElo',
  elo: 'Elo-Daten', espn: 'ESPN', fotmob: 'FotMob',
}

function sourceName(value: unknown): string {
  if (typeof value !== 'string' || !value || value === 'none') return 'Quelle nicht belegt'
  return value.split('+').map(part => sourceLabels[part] ?? part.replaceAll('_', ' ')).join(' + ')
}

function sourceRow(key: string, label: string, available: boolean, metadata: Record<string, unknown>, now: number): MatchDataRow {
  const timestamp = typeof metadata.observed_at === 'string' ? Date.parse(metadata.observed_at) : NaN
  const observedAt = Number.isFinite(timestamp) && timestamp <= now ? metadata.observed_at as string : null
  let status: DataStatus
  if (!available || metadata.status === 'unavailable') status = 'unavailable'
  else if (metadata.status === 'failed') status = 'failed'
  else if (metadata.status === 'stale' || (observedAt && now - timestamp > 86_400_000)) status = 'stale'
  else if (metadata.status === 'fresh' && observedAt) status = 'fresh'
  else status = 'unknown'
  const message = {
    fresh: 'Datenstand belegt', stale: 'Älterer Datenstand', failed: 'Abruf fehlgeschlagen',
    unavailable: 'Nicht verfügbar', unknown: 'Aktualität nicht bestätigt', partial: 'Teilweise erfasst',
  }[status]
  return { key, label, status, source: sourceName(metadata.source), observedAt, message }
}

export function buildMatchDataStatus(match: Match, now = Date.now(), prediction?: Prediction): MatchDataStatus {
  const inputs = prediction ?? match
  const provenance = inputs.input_provenance ?? inputs.provenance ?? {}
  const oddsMeta = provenance.odds as Record<string, unknown> | undefined
  const eloMeta = provenance.elo as Record<string, unknown> | undefined
  const hasOdds = prediction
    ? ['odds+elo', 'odds-only'].includes(prediction.source_mode ?? '')
    : Boolean(match.odds && [match.odds.home, match.odds.draw, match.odds.away].every(value => Number.isFinite(value) && value > 1))
  const hasElo = ['odds+elo', 'elo-only'].includes(inputs.source_mode ?? '')
    || (!prediction && match.source_mode == null && typeof match.elo_home_share === 'number' && Number.isFinite(match.elo_home_share) && match.elo_home_share >= 0 && match.elo_home_share <= 1)
  const odds = sourceRow('odds', 'Buchmacherquoten', hasOdds, {
    ...oddsMeta, observed_at: oddsMeta?.observed_at ?? (prediction ? null : match.odds_observed_at),
    source: oddsMeta?.source ?? (prediction ? undefined : match.odds_provenance?.source),
  }, now)
  const elo = sourceRow('elo', 'Elo-Teamstärke', hasElo, eloMeta ?? {}, now)
  const intelligence = match.match_intelligence
  const lineupInfo = lineupState(intelligence, match.home_team, match.away_team)
  const lineup = sourceRow('lineups', 'Aufstellungen', lineupInfo.kind === 'confirmed', intelligence as unknown as Record<string, unknown> ?? {}, now)
  if (lineupInfo.kind === 'unavailable') {
    if (lineupInfo.partial) lineup.status = 'partial'
    else if (intelligence?.status === 'failed' || ['provider_error', 'fetch_failed'].includes(intelligence?.reason ?? '')) lineup.status = 'failed'
    lineup.message = lineupInfo.message
  }
  const rows = [odds, elo, lineup]
  let status: DataStatus = 'partial'
  let title = 'Aktualität nicht bestätigt'
  let explanation = 'Die Aktualität der gespeicherten Eingaben ist nicht vollständig belegt.'
  if (!hasOdds && !hasElo) {
    status = 'unavailable'
    title = 'Eingaben nicht belegt'
    explanation = 'Weder Buchmacherquoten noch Elo-Werte für beide Teams sind belegt.'
  } else if (!hasOdds) {
    title = 'Elo ohne Buchmacherquoten'
    explanation = 'Die Empfehlung nutzt nur Elo; Buchmacherquoten fehlen.'
  } else if (!hasElo) {
    title = 'Quoten ohne Elo'
    explanation = 'Buchmacherquoten sind erfasst; Elo-Werte für beide Teams sind nicht belegt.'
  }
  if ([odds, elo].some(row => row.status === 'stale' || row.status === 'failed')) {
    status = 'stale'
    title = 'Älterer Datenstand'
    explanation += ' Mindestens eine Quelle ist veraltet oder ihr Abruf ist fehlgeschlagen.'
  } else if (odds.status === 'fresh' && elo.status === 'fresh') {
    status = 'fresh'
    title = 'Datenstand belegt'
    explanation = 'Quoten und Elo wurden innerhalb der letzten 24 Stunden erfasst. Das ist keine Aussage über die Trefferchance.'
  }
  return { status, title, explanation, rows }
}
