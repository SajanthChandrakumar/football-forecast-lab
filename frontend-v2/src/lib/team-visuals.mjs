export function collectTeamLogos(matches = [], standings = []) {
  const logos = {}
  const add = (team, logo) => {
    if (typeof team === 'string' && team.trim() && typeof logo === 'string' && logo.trim()) {
      logos[team.trim()] = logo.trim()
    }
  }

  for (const match of matches) {
    add(match.home_team, match.home_logo)
    add(match.away_team, match.away_logo)
  }
  for (const group of standings) {
    for (const row of group.rows ?? []) add(row.team, row.logo)
  }
  return logos
}
