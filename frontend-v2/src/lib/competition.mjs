export const COMPETITIONS = ['wc2026', 'ucl2026']

export function validCompetition(value, registered = COMPETITIONS) {
  return typeof value === 'string' && registered.includes(value) ? value : 'ucl2026'
}

export function competitionPath(path, competition) {
  const joiner = path.includes('?') ? '&' : '?'
  return `${path}${joiner}competition=${encodeURIComponent(competition)}`
}

export function competitionLabel(competition, competitions = []) {
  return competitions.find((item) => item.id === competition)?.short_name
    ?? (competition === 'ucl2026' ? 'UCL 2026/27' : competition === 'wc2026' ? 'WM 2026' : competition)
}
