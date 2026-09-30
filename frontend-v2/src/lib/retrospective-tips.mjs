const STORAGE_PREFIX = 'football-forecast-lab:private-retrospective-tips:v1:'

const TEAM_ALIASES = {
  'aek athen': 'aek athens',
  'linzer ask': 'lask',
  brugge: 'club brugge',
  'sporting lissabon': 'sporting cp',
  'paris st germain': 'paris saint germain',
  'inter mailand': 'inter milan',
  'betis sevilla': 'real betis',
  'schachtar donezk': 'shakhtar donetsk',
  'slavia prag': 'slavia prague',
  'viking stavanger': 'viking fk',
  'bayern munchen': 'bayern munich',
  fenerbahce: 'fenerbahce istanbul',
}

function teamKey(value) {
  let key = String(value ?? '')
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
    .replace(/^(?:fc|fk|cf|afc|ssc)\s+/, '')
  return TEAM_ALIASES[key] ?? key
}

function scoreTip(tip, actual, isKnockout) {
  const tipScore = tip.split(':').map(Number)
  const actualScore = actual.split(':').map(Number)
  const [tipHome, tipAway] = tipScore
  const [actualHome, actualAway] = actualScore
  const tipTendency = Math.sign(tipHome - tipAway)
  const actualTendency = Math.sign(actualHome - actualAway)
  const tendencyCorrect = tipTendency === actualTendency
  let points = (tendencyCorrect ? 5 : 0)
    + (tipHome === actualHome ? 1 : 0)
    + (tipAway === actualAway ? 1 : 0)
    + (tendencyCorrect && tipHome - tipAway === actualHome - actualAway ? 3 : 0)
  if (isKnockout) points *= 2
  return points
}

function storageKey(competition) {
  return `${STORAGE_PREFIX}${competition}`
}

export function readRetrospectiveTips(competition, storage = globalThis.localStorage) {
  try {
    return JSON.parse(storage?.getItem(storageKey(competition)) ?? '{}')
  } catch {
    return {}
  }
}

export function importRetrospectiveTips(competition, rows, archive, storage = globalThis.localStorage) {
  if (!Array.isArray(rows)) throw new Error('Die Importdatei muss eine JSON-Liste enthalten.')
  if (!storage) throw new Error('Dieser Browser bietet keinen privaten lokalen Speicher an.')

  const saved = readRetrospectiveTips(competition, storage)
  const errors = []
  let imported = 0
  let points = 0

  rows.forEach((row, index) => {
    const date = /^\d{4}-\d{2}-\d{2}$/.test(row?.date ?? '') ? row.date : ''
    const tip = /^\d{1,2}:\d{1,2}$/.test(row?.tip ?? '') ? row.tip : ''
    const homeKey = teamKey(row?.home_team)
    const awayKey = teamKey(row?.away_team)
    if (!date || !tip || !homeKey || !awayKey) {
      errors.push(`Zeile ${index + 1}: Datum, Heimteam, Auswärtsteam oder Tipp fehlt.`)
      return
    }

    const matches = Object.entries(archive ?? {}).filter(([, entry]) =>
      entry?.post_match_result?.status === 'completed'
      && entry?.metadata?.commence_time?.slice(0, 10) === date
      && teamKey(entry.metadata.home_team) === homeKey
      && teamKey(entry.metadata.away_team) === awayKey)

    if (matches.length !== 1) {
      errors.push(`Zeile ${index + 1}: Spiel nicht eindeutig im Archiv gefunden (${row.home_team} – ${row.away_team}, ${date}).`)
      return
    }

    const [id, entry] = matches[0]
    const actual = entry.post_match_result.actual_score
    if (!/^\d{1,2}:\d{1,2}$/.test(actual ?? '') || (row.actual_score && row.actual_score !== actual)) {
      errors.push(`Zeile ${index + 1}: Ergebnis passt nicht zum Archiv (${actual ?? 'fehlt'}).`)
      return
    }

    const earned = scoreTip(tip, actual, entry.metadata.is_ko_phase === true)
    if (row.points != null && (!Number.isInteger(row.points) || row.points !== earned)) {
      errors.push(`Zeile ${index + 1}: angegebene Punkte (${row.points}) passen nicht zur SRF-Wertung (${earned}).`)
      return
    }

    saved[id] = {
      user_tip: tip,
      points: earned,
      actual_score: actual,
      saved_at: new Date().toISOString(),
    }
    imported++
    points += earned
  })

  storage.setItem(storageKey(competition), JSON.stringify(saved))
  return { imported, points, errors }
}

export function applyRetrospectiveTips(archive, localTips) {
  const result = { ...(archive ?? {}) }
  for (const [id, saved] of Object.entries(localTips ?? {})) {
    const entry = result[id]
    if (!entry || entry.post_match_result?.status !== 'completed') continue
    result[id] = {
      ...entry,
      prediction: { ...entry.prediction, user_tip: saved.user_tip, local_user_tip: true },
      post_match_result: { ...entry.post_match_result, points_earned: saved.points },
    }
  }
  return result
}
