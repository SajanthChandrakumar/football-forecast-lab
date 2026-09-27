import { validUclStandingsRows } from './standings.mjs'

// Keep this in sync with the club aliases in src/constants.py TEAM_MAPPING.
// Resolve only to keys that the Elo API actually returned.
const CLUB_TEAM_ALIASES = {
  'Club Brugge': 'Brugge',
  'Manchester City': 'Man City',
  'FC Porto': 'Porto',
  'Borussia Dortmund': 'Dortmund',
  'Real Betis': 'Betis',
  Internazionale: 'Inter',
  'VfB Stuttgart': 'Stuttgart',
  'Feyenoord Rotterdam': 'Feyenoord',
  'AEK Athens': 'AEK',
  'LASK Linz': 'LASK',
  'Viking FK': 'Viking',
  'AS Roma': 'Roma',
  'Atlético Madrid': 'Atlético',
  'Atletico Madrid': 'Atlético',
  'Bodo/Glimt': 'Bodø/Glimt',
  'Bodø/Glimt': 'Bodø/Glimt',
  Fenerbahce: 'Fenerbahçe',
  'Manchester United': 'Man United',
  'PSV Eindhoven': 'PSV',
  'Shakhtar Donetsk': 'Shakhtar',
  'Slavia Prague': 'Slavia Praha',
  'Slavia Praha': 'Slavia Praha',
  'Slovan Bratislava': 'Slovan',
  'Sporting CP': 'Sporting',
  'Sporting Lisbon': 'Sporting',
  'Paris Saint Germain': 'Paris Saint-Germain',
  'ŠK Slovan Bratislava': 'Slovan',
  'RC Lens': 'Lens',
}

export function teamFormCanonicalName(team) {
  return CLUB_TEAM_ALIASES[team] ?? team
}

function ratingKeyFor(team, available) {
  const canonical = teamFormCanonicalName(team)
  return available.has(team) ? team : available.has(canonical) ? canonical : null
}

export function teamFormCoverage(competition, teams, standingsRows = []) {
  if (competition !== 'ucl2026') {
    return { complete: true, standingsValid: true, required: teams.length, available: teams.length, missing: [] }
  }
  const rows = validUclStandingsRows(standingsRows)
  if (!rows) return { complete: false, standingsValid: false, required: 36, available: 0, missing: [] }
  const available = new Set(teams)
  const missing = rows.filter(({ team }) => !ratingKeyFor(team, available)).map(({ team }) => team)
  return {
    complete: missing.length === 0,
    standingsValid: true,
    required: rows.length,
    available: rows.length - missing.length,
    missing,
  }
}

export function teamFormSnapshotState(ratingCoverage, snapshotStatus) {
  const snapshotCoverage = snapshotStatus?.coverage
  const snapshotMissing = Array.isArray(snapshotCoverage?.missing)
    ? snapshotCoverage.missing
    : ratingCoverage.missing
  const status = snapshotStatus?.status ?? null
  return {
    ...ratingCoverage,
    status,
    showRatings: ratingCoverage.complete,
    showAlert: !ratingCoverage.complete || status !== 'fresh' || snapshotMissing.length > 0,
    snapshotAvailable: snapshotCoverage?.available ?? ratingCoverage.available,
    snapshotRequired: snapshotCoverage?.required ?? ratingCoverage.required,
    snapshotMissing,
    error: snapshotStatus?.error ?? null,
  }
}

export function teamFormEntries(competition, teams, standingsRows = []) {
  if (competition !== 'ucl2026') return teams.map((team) => ({ team, ratingKey: team }))
  const rows = validUclStandingsRows(standingsRows)
  if (!rows) return []
  const available = new Set(teams)
  if (!teamFormCoverage(competition, teams, rows).complete) return []
  return rows.map(({ team }) => ({ team, ratingKey: ratingKeyFor(team, available) }))
}

export function teamFormTeamNames(competition, teams, standingsRows = []) {
  return teamFormEntries(competition, teams, standingsRows).map(({ team }) => team)
}

export function teamsWithoutHistory(teams, history = {}) {
  return teams.filter((team) => !history[team]?.length)
}
