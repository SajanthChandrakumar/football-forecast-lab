import { teamFormCanonicalName } from './team-form.mjs'

export function sanitizeTeamSelection(teams) {
  if (!Array.isArray(teams)) return []
  const selected = []
  const seen = new Set()
  for (const value of teams) {
    if (typeof value !== 'string') continue
    const team = value.trim()
    if (!team || seen.has(team)) continue
    seen.add(team)
    selected.push(team)
    if (selected.length === 4) break
  }
  return selected
}

function storageKey(competition) {
  return `team-comparison:${competition}`
}

export function readTeamSelection(competition, storage = globalThis.localStorage) {
  try {
    const stored = storage?.getItem(storageKey(competition))
    if (stored == null) return null
    const parsed = JSON.parse(stored)
    return Array.isArray(parsed) ? sanitizeTeamSelection(parsed) : null
  } catch {
    return null
  }
}

export function writeTeamSelection(competition, teams, storage = globalThis.localStorage) {
  const selected = sanitizeTeamSelection(teams)
  try { storage?.setItem(storageKey(competition), JSON.stringify(selected)) } catch { /* Keep the selection in memory when storage is unavailable. */ }
  return selected
}

function availableName(name, namesByCanonical) {
  if (typeof name !== 'string') return null
  const team = name.trim()
  if (!team) return null
  return namesByCanonical.get(team) ?? namesByCanonical.get(teamFormCanonicalName(team)) ?? null
}

export function resolveInitialTeamSelection(savedSelection, matches, rows, now = Date.now()) {
  const namesByCanonical = new Map()
  for (const { team } of rows ?? []) {
    if (typeof team !== 'string' || !team.trim()) continue
    const name = team.trim()
    namesByCanonical.set(name, name)
    namesByCanonical.set(teamFormCanonicalName(name), name)
  }

  if (savedSelection != null) {
    return sanitizeTeamSelection(savedSelection.map((name) => availableName(name, namesByCanonical) ?? name))
  }

  const nextFixture = (matches ?? [])
    .map((match, index) => ({ match, index, kickoff: Date.parse(match.raw_match?.commence_time ?? '') }))
    .filter(({ match, kickoff }) => Number.isFinite(kickoff) && kickoff > now && !match.completed && !match.actual_score)
    .sort((a, b) => a.kickoff - b.kickoff || a.index - b.index)
    .map(({ match }) => [
      availableName(match.home_team, namesByCanonical),
      availableName(match.away_team, namesByCanonical),
    ])
    .find(([home, away]) => home && away && home !== away)

  return sanitizeTeamSelection(nextFixture ?? (rows ?? []).slice(0, 2).map(({ team }) => team))
}
