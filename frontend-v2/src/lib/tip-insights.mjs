export function rankedTipInsights(tips = [], matrix, limit = 3) {
  return tips
    .filter((item) => typeof item?.Tipp === 'string' && Number.isFinite(item.xP))
    .sort((a, b) => b.xP - a.xP)
    .slice(0, limit)
    .map(({ Tipp, xP }) => {
      const [home, away] = Tipp.split(':').map(Number)
      const chance = matrix?.[home]?.[away]
      return {
        tip: Tipp,
        expectedPoints: xP,
        exactChance: Number.isFinite(chance) && chance >= 0 ? chance : null,
      }
    })
}

export function scoreProbabilitySummary(matrix, modelTip) {
  if (!matrix) return null
  const scores = Object.entries(matrix).flatMap(([home, row]) =>
    Object.entries(row ?? {}).flatMap(([away, chance]) =>
      Number.isFinite(chance) && chance >= 0
        ? [{ tip: `${home}:${away}`, chance }]
        : [],
    ),
  )
  if (!scores.length) return null
  scores.sort((a, b) => b.chance - a.chance || a.tip.localeCompare(b.tip))
  const modelTipChance = scores.find((score) => score.tip === modelTip)?.chance ?? null
  return { topScores: scores.slice(0, 3), modelTipChance }
}

export function recentFormSummary(form) {
  const results = form?.form?.slice(-10) ?? []
  if (!results.length) return 'Form nicht verfügbar'
  const labels = [
    ['W', 'Sieg', 'Siege'],
    ['D', 'Unentschieden', 'Unentschieden'],
    ['L', 'Niederlage', 'Niederlagen'],
  ]
  const parts = labels.flatMap(([key, singular, plural]) => {
    const count = results.filter((result) => result === key).length
    return count ? [`${count} ${count === 1 ? singular : plural}`] : []
  })
  return `Letzte ${results.length}: ${parts.join(', ')}`
}

export function teamHistoryAnalysis(form) {
  const matches = (form?.matches ?? []).slice(0, 10).filter((match) => (
    Number.isFinite(match?.goals_for) && Number.isFinite(match?.goals_against)
  ))
  if (!matches.length) return null
  const wins = matches.filter((match) => match.result === 'W').length
  const draws = matches.filter((match) => match.result === 'D').length
  const goalsFor = matches.reduce((total, match) => total + match.goals_for, 0) / matches.length
  const goalsAgainst = matches.reduce((total, match) => total + match.goals_against, 0) / matches.length
  const pointsPerGame = (wins * 3 + draws) / matches.length
  const trend = pointsPerGame >= 2 && goalsFor - goalsAgainst >= 0.5
    ? 'Starke Form'
    : pointsPerGame < 1 || goalsAgainst - goalsFor >= 0.5
      ? 'Schwache Form'
      : 'Ausgeglichene Form'
  return `${trend} · ${wins} ${wins === 1 ? 'Sieg' : 'Siege'} aus ${matches.length} · Ø ${goalsFor.toFixed(1)}:${goalsAgainst.toFixed(1)} Tore`
}

export function teamHistoryMetrics(form) {
  const matches = (form?.matches ?? []).slice(0, 10).filter((match) => (
    Number.isFinite(match?.goals_for) && Number.isFinite(match?.goals_against)
  ))
  if (!matches.length) return null
  const goalsFor = matches.reduce((total, match) => total + match.goals_for, 0)
  const goalsAgainst = matches.reduce((total, match) => total + match.goals_against, 0)
  return {
    matches: matches.length,
    goalsFor,
    goalsAgainst,
    averageFor: goalsFor / matches.length,
    averageAgainst: goalsAgainst / matches.length,
    cleanSheets: matches.filter((match) => match.goals_against === 0).length,
    bothTeamsScored: matches.filter((match) => match.goals_for > 0 && match.goals_against > 0).length,
  }
}

export function matchFormInsights(homeName, homeForm, awayName, awayForm) {
  const recent = (form) => (form?.matches ?? []).slice(0, 10).filter((match) => (
    ['W', 'D', 'L'].includes(match?.result)
    && Number.isFinite(match?.goals_for)
    && Number.isFinite(match?.goals_against)
  ))
  const home = recent(homeForm)
  const away = recent(awayForm)
  if (home.length < 3 || away.length < 3) return []

  const homeWins = home.filter((match) => match.result === 'W').length
  const awayWins = away.filter((match) => match.result === 'W').length
  const homeLeads = homeWins / home.length > awayWins / away.length
  const formLead = Math.abs(homeWins / home.length - awayWins / away.length) >= 0.2
  const leader = homeLeads
    ? { name: homeName, wins: homeWins, games: home.length }
    : { name: awayName, wins: awayWins, games: away.length }
  const other = homeLeads
    ? { name: awayName, wins: awayWins, games: away.length }
    : { name: homeName, wins: homeWins, games: home.length }
  const formInsight = {
    kind: 'form',
    title: formLead ? `${leader.name} zuletzt in besserer Form` : 'Kein klarer Formvorteil',
    detail: formLead
      ? `${leader.wins} ${leader.wins === 1 ? 'Sieg' : 'Siege'} in ${leader.games} erfassten Spielen. ${other.name} gewann ${other.wins} von ${other.games}.`
      : `${homeName}: ${homeWins} ${homeWins === 1 ? 'Sieg' : 'Siege'} aus ${home.length} Spielen. ${awayName}: ${awayWins} ${awayWins === 1 ? 'Sieg' : 'Siege'} aus ${away.length}.`,
  }

  const homeScored = home.filter((match) => match.goals_for > 0).length
  const awayScored = away.filter((match) => match.goals_for > 0).length
  const homeConceded = home.filter((match) => match.goals_against > 0).length
  const awayConceded = away.filter((match) => match.goals_against > 0).length
  const homeAttackSignal = Math.min(homeScored / home.length, awayConceded / away.length)
  const awayAttackSignal = Math.min(awayScored / away.length, homeConceded / home.length)
  const strongerSignal = Math.max(homeAttackSignal, awayAttackSignal) >= 0.6
  const awaySignal = awayAttackSignal >= homeAttackSignal
  const scoringName = awaySignal ? awayName : homeName
  const concedingName = awaySignal ? homeName : awayName
  const scored = awaySignal ? awayScored : homeScored
  const scoringGames = awaySignal ? away.length : home.length
  const conceded = awaySignal ? homeConceded : awayConceded
  const concedingGames = awaySignal ? home.length : away.length
  return [formInsight, {
    kind: 'goals',
    title: strongerSignal ? `${scoringName} trifft regelmäßig` : 'Kein klares Torsignal',
    detail: `Tor in ${scored} von ${scoringGames} Spielen. ${concedingName} kassierte in ${conceded} von ${concedingGames} ein Gegentor.`,
  }]
}

export function playerFormSummary(player) {
  const appearances = `${player.appearances} ${player.appearances === 1 ? 'Einsatz' : 'Einsätze'}`
  const parts = []
  if (Number.isFinite(player.goals)) parts.push(`${player.goals} ${player.goals === 1 ? 'Tor' : 'Tore'}`)
  if (Number.isFinite(player.assists)) parts.push(`${player.assists} ${player.assists === 1 ? 'Assist' : 'Assists'}`)
  return [...parts, appearances].join(' · ')
}

export function playerFormStatusMessage(playerForm) {
  const sampled = playerForm?.matches_sampled ?? 0
  const minimum = playerForm?.minimum_matches ?? 3
  if (playerForm?.reason === 'no_contributions' && sampled >= minimum) {
    return `In ${sampled} archivierten Spielen wurden keine individuellen Tore oder Assists erfasst.`
  }
  return `Noch zu wenig echte Spielerdaten (${sampled} von ${minimum} Spielen archiviert).`
}

export function matchLoadSummary(form, kickoff) {
  const kickoffTime = Date.parse(kickoff)
  const observedTime = Date.parse(form?.observed_at)
  const day = 24 * 60 * 60 * 1000
  if (!Number.isFinite(kickoffTime) || !Number.isFinite(observedTime)
    || observedTime > kickoffTime || kickoffTime - observedTime > 2 * day
    || !Array.isArray(form?.matches)) return null

  const played = form.matches
    .map((match) => Date.parse(match?.played_at))
    .filter((time) => Number.isFinite(time) && time < kickoffTime)
  if (!played.length) return null

  const restDays = Math.floor((kickoffTime - Math.max(...played)) / day)
  const recentGames = played.filter((time) => time >= kickoffTime - 14 * day).length
  const rest = restDays === 0 ? 'Unter 1 Tag Pause' : `${restDays} ${restDays === 1 ? 'Tag' : 'Tage'} Pause`
  return `${rest} · ${recentGames} erfasste ${recentGames === 1 ? 'Spiel' : 'Spiele'} in 14 Tagen`
}
