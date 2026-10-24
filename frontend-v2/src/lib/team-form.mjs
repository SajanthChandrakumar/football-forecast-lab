import { validPremierLeagueStandingsRows, validUclStandingsRows } from './standings.mjs'

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
  'AFC Bournemouth': 'Bournemouth',
  'Brighton & Hove Albion': 'Brighton',
  'Brighton and Hove Albion': 'Brighton',
  'Coventry City': 'Coventry',
  'Hull City': 'Hull',
  'Ipswich Town': 'Ipswich',
  'Leeds United': 'Leeds',
  'Newcastle United': 'Newcastle',
  'Nottingham Forest': 'Forest',
  'Tottenham Hotspur': 'Tottenham',
}

export function teamFormCanonicalName(team) {
  return CLUB_TEAM_ALIASES[team] ?? team
}

function ratingKeyFor(team, available) {
  const canonical = teamFormCanonicalName(team)
  return available.has(team) ? team : available.has(canonical) ? canonical : null
}

export function teamFormCoverage(competition, teams, standingsRows = []) {
  if (competition === 'epl2026') {
    const rows = validPremierLeagueStandingsRows(standingsRows)
    if (!rows) return { complete: false, standingsValid: false, required: 20, available: 0, missing: [] }
    const available = new Set(teams)
    const missing = rows.filter(({ team }) => !ratingKeyFor(team, available)).map(({ team }) => team)
    return { complete: missing.length === 0, standingsValid: true, required: 20, available: 20 - missing.length, missing }
  }
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
  if (competition === 'epl2026') {
    const rows = validPremierLeagueStandingsRows(standingsRows)
    if (!rows) return []
    const available = new Set(teams)
    return rows.flatMap(({ team }) => {
      const ratingKey = ratingKeyFor(team, available)
      return ratingKey ? [{ team, ratingKey }] : []
    })
  }
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

export function verifiedClubFormMatches(form, { before, competition = 'all' } = {}) {
  if (form?.scope !== 'all_competitions') return []
  const cutoff = before === undefined ? Infinity : Date.parse(before)
  if (!Number.isFinite(cutoff) && cutoff !== Infinity) return []
  const ordered = (form.matches ?? [])
    .filter((match) => {
      const playedAt = Date.parse(match?.played_at ?? '')
      if (match?.identity_verified !== true || !['league', 'cup', 'europe'].includes(match?.competition_kind)
        || !match.fixture_id || !match.home_id || !match.home_team || !match.away_id || !match.away_team
        || !['W', 'D', 'L'].includes(match.result) || !['home', 'away'].includes(match.venue)
        || typeof match.score !== 'string'
        || !Number.isFinite(playedAt) || playedAt >= cutoff
        || (competition !== 'all' && match.competition_kind !== competition)) return false
      return true
    })
    .sort((a, b) => Date.parse(b.played_at) - Date.parse(a.played_at) || a.fixture_id.localeCompare(b.fixture_id))
  const seen = new Set()
  return ordered.filter((match) => {
    if (seen.has(match.fixture_id)) return false
    seen.add(match.fixture_id)
    return true
  })
}

export function clubFormSummary(matches) {
  return (matches ?? []).reduce((summary, match) => {
    summary.played += 1
    if (match.result === 'W') summary.wins += 1
    else if (match.result === 'D') summary.draws += 1
    else if (match.result === 'L') summary.losses += 1
    if (Number.isFinite(match.goals_for)) summary.goalsFor += match.goals_for
    if (Number.isFinite(match.goals_against)) summary.goalsAgainst += match.goals_against
    return summary
  }, { played: 0, wins: 0, draws: 0, losses: 0, goalsFor: 0, goalsAgainst: 0 })
}

export function clubFormHomeAwayScore(match) {
  const [first, second] = typeof match?.score === 'string' ? match.score.split(':').map(Number) : []
  const goalsFor = Number.isFinite(match?.goals_for) ? match.goals_for : first
  const goalsAgainst = Number.isFinite(match?.goals_against) ? match.goals_against : second
  if (!Number.isFinite(goalsFor) || !Number.isFinite(goalsAgainst) || !['home', 'away'].includes(match?.venue)) return null
  return match.venue === 'home' ? `${goalsFor}:${goalsAgainst}` : `${goalsAgainst}:${goalsFor}`
}

export function clubFormForTeam(team, fixtures = []) {
  const target = teamFormCanonicalName(team)
  const forms = fixtures.flatMap((fixture) => {
    const rows = []
    if (teamFormCanonicalName(fixture.home_team ?? '') === target && fixture.home_form) rows.push(fixture.home_form)
    if (teamFormCanonicalName(fixture.away_team ?? '') === target && fixture.away_form) rows.push(fixture.away_form)
    return rows
  }).filter((form) => form.scope === 'all_competitions')
  if (!forms.length) return null
  const matches = verifiedClubFormMatches({ scope: 'all_competitions', matches: forms.flatMap((form) => form.matches ?? []) })
  const coverage = forms.reduce((best, form) => {
    if (!form.coverage) return best
    return !best || form.coverage.available > best.available ? form.coverage : best
  }, null)
  return {
    form: matches.slice(0, 10).reverse().map((match) => match.result),
    on_fire: matches.length >= 3 && matches.slice(0, 3).every((match) => match.result === 'W'),
    scope: 'all_competitions',
    status: forms.some((form) => form.status === 'stale') ? 'stale' : forms.find((form) => form.status)?.status ?? 'unavailable',
    source: [...new Set(forms.map((form) => form.source).filter(Boolean))].join(' + ') || undefined,
    observed_at: forms.map((form) => form.observed_at).filter(Boolean).sort().at(-1) ?? null,
    coverage,
    validation_version: forms.find((form) => form.validation_version)?.validation_version,
    matches,
  }
}

export function chronologicalRecentMatches(matches, limit = 5) {
  const chronological = (matches ?? []).map((match, index) => ({
    match,
    index,
    timestamp: Date.parse(match.playedAt ?? ''),
  })).sort((a, b) => {
    const aKnown = Number.isFinite(a.timestamp)
    const bKnown = Number.isFinite(b.timestamp)
    if (aKnown !== bKnown) return aKnown ? 1 : -1
    return (aKnown ? a.timestamp - b.timestamp : 0) || a.index - b.index
  })
  return chronological.slice(-Math.max(0, Math.trunc(limit))).map(({ match }) => match)
}

export function formatEloTimestamp(timestamp) {
  if (timestamp === 0) return 'Beginn'
  if (!Number.isFinite(timestamp)) return 'Zeitpunkt nicht verfügbar'
  return new Date(timestamp * 1_000).toLocaleDateString('de-CH', {
    day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'Europe/Zurich',
  })
}
