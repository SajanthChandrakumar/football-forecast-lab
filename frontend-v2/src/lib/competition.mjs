export const FALLBACK_COMPETITIONS = [
  { id: 'wc2026', short_name: 'WM 2026', display_name: 'World Cup 2026' },
  { id: 'ucl2026', short_name: 'UCL 2026/27', display_name: 'Champions League 2026/27' },
  { id: 'epl2026', short_name: 'PL 2026/27', display_name: 'Premier League 2026/27' },
]

export const COMPETITIONS = FALLBACK_COMPETITIONS.map(({ id }) => id)

export function validCompetition(value, registered = COMPETITIONS) {
  return typeof value === 'string' && registered.includes(value) ? value : 'ucl2026'
}

export function competitionPath(path, competition) {
  const joiner = path.includes('?') ? '&' : '?'
  return `${path}${joiner}competition=${encodeURIComponent(competition)}`
}

export function competitionLabel(competition, competitions = []) {
  return competitions.find((item) => item.id === competition)?.short_name
    ?? FALLBACK_COMPETITIONS.find((item) => item.id === competition)?.short_name
    ?? competition
}
