import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { useArchive, useMatchHistory, useMatches, usePoolContext, usePredict, useSavePoolContext } from '../../hooks/queries'
import { useAppState } from '../../state/AppState'
import { computeImpliedProbs, pct } from '../../lib/util'
import { kickoffTime, shortDate } from '../../lib/format'
import { fixtureStatus } from '../../lib/fixture-status.mjs'
import type { BotKey, Match, TeamForm, TeamFormMatch, MatchLineup, MatchPlayer } from '../../lib/types'
import { FormBadges, TeamLogo } from '../../components/shared/Badges'
import { MatchHintCard } from '../../components/shared/MatchHintCard'
import { MatchDataStatus } from '../../components/shared/MatchDataStatus'
import { SharedTipEditor } from '../../components/shared/SharedTipEditor'
import { OutcomeBar } from '../../components/shared/OutcomeBar'
import { PageTransition } from '../../components/shared/PageTransition'
import { QueryState } from '../../components/shared/QueryState'
import { ChartSkeleton, Skeleton } from '../../components/shared/Skeleton'
import { GlassCard, SectionTitle } from '../../components/shared/GlassCard'
import { ViewPanel, ViewTabs } from '../../components/shared/ViewTabs'
import { useView } from '../../hooks/useView'
import { OddsHistory } from './OddsHistory'
import { ClubTeamFormHistory } from '../team-form/ClubTeamFormHistory'
import { verifiedClubFormMatches } from '../../lib/team-form.mjs'
import { lineupState } from '../../lib/match-intelligence.mjs'
import { lineupRows } from '../../lib/lineup-layout.mjs'
import { ScoreHeatmap } from './ScoreHeatmap'
import { formatObservedAt, parseTipCountRows } from './detail-form.mjs'
import type { TipCountRow } from './detail-form.mjs'
import { rankedTipInsights, recentFormSummary, matchLoadSummary, playerFormStatusMessage, playerFormSummary, teamHistoryAnalysis, teamHistoryMetrics } from '../../lib/tip-insights.mjs'

const BOT_LABELS: Record<BotKey, string> = {
  broker: 'Broker',
  professor: 'Professor',
  sniper: 'X-Sniper',
  gambler: 'Zocker',
}

const stageLabels: Record<string, string> = {
  'League stage': 'Ligaphase',
  league: 'Ligaphase',
  group: 'Gruppenphase',
  'Round of 16': 'Achtelfinale',
  'Quarter-finals': 'Viertelfinale',
  'Semi-finals': 'Halbfinale',
  'Final': 'Finale',
}

type PoolForm = {
  user_points: string
  leader_points: string
  remaining_srf_max_points: string
  tipRows: TipCountRow[]
}

const EMPTY_POOL_FORM: PoolForm = {
  user_points: '',
  leader_points: '',
  remaining_srf_max_points: '',
  tipRows: [{ tip: '', count: '' }],
}

const MATCH_VIEWS = [
  { value: 'overview', label: 'Überblick' },
  { value: 'form', label: 'Form' },
  { value: 'lineups', label: 'Aufstellungen' },
  { value: 'market', label: 'Markt' },
  { value: 'model', label: 'Modelldaten' },
] as const

type MatchView = typeof MATCH_VIEWS[number]['value']

function outcomeSourceLabel(sourceMode?: string | null, source?: string | null) {
  if (sourceMode === 'odds+elo') return 'Buchmacherquoten + Elo-Modell'
  if (sourceMode === 'odds-only') return 'Buchmacherquoten'
  if (sourceMode === 'elo-only') return 'Elo-Modell'
  if (source === 'odds_api') return 'The Odds API'
  if (source === 'clubelo') return 'ClubElo'
  if (source === 'api_football') return 'API-Football'
  return 'Gespeicherte Modellwerte'
}

function stageLabel(stage?: string) {
  if (!stage) return 'Spiel'
  return stageLabels[stage] ?? stage.replaceAll('_', ' ')
}

function matchStatusLabel(match: Match, now: number) {
  const status = fixtureStatus(match, now)
  return {
    upcoming: 'Bevorstehend',
    played: 'Abgeschlossen',
    pending: 'Ergebnis ausstehend',
    unscheduled: 'Anstoßzeit offen',
  }[status]
}

function requestErrorMessage(error: unknown) {
  const message = error instanceof Error ? error.message : ''
  if (message.startsWith('409')) return 'Der Kontext konnte nicht gespeichert werden, weil die Anfrage abgelehnt wurde.'
  return 'Der Kontext konnte nicht gespeichert werden. Bitte prüfe die Eingaben und versuche es erneut.'
}

function TeamFormHistory({ team, form, kickoff, showHistoricalLineups = true }: { team: string; form?: TeamForm; kickoff?: string; showHistoricalLineups?: boolean }) {
  if (!form?.status && !form?.matches?.length) return null
  const items = form?.matches?.slice(0, 10) ?? []
  const load = matchLoadSummary(form, kickoff)
  const analysis = teamHistoryAnalysis(form)
  const metrics = teamHistoryMetrics(form)
  const playerForm = form?.player_form
  const leagueScoped = form?.scope === 'league'
  const sourceLabel = form?.source === 'espn+fotmob'
    ? 'ESPN + FotMob'
    : form?.source === 'espn'
      ? 'ESPN'
      : form?.source === 'api_football'
        ? 'API-Football'
        : form?.source
  return (
    <section className="rounded-xl border border-line bg-surface p-4 text-left">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-base font-bold text-fg">{team}</h3>
          <p className="mt-1 text-xs text-fg-2">
            {leagueScoped ? 'Letzte erfasste Premier-League-Spiele' : 'Letzte Pflichtspiele · alle Wettbewerbe'}{sourceLabel ? ` · Quelle: ${sourceLabel}` : ''}
          </p>
          {leagueScoped && <p className="mt-1 text-xs text-fg-3">Die Form umfasst nur zuletzt erfasste Premier-League-Spiele, keine anderen Wettbewerbe.</p>}
        </div>
        {form?.status === 'stale' && <span className="text-xs font-semibold text-amber-a">Stand möglicherweise veraltet</span>}
      </div>
      {load ? (
        <p className="mt-3 rounded-lg bg-surface-2 px-3 py-2 text-xs font-semibold text-fg-2">{load}</p>
      ) : items.length > 0 && kickoff && Date.parse(kickoff) > Date.now() ? (
        <p className="mt-3 rounded-lg bg-surface-2 px-3 py-2 text-xs font-semibold text-fg-2">Belastung kurz vor Anpfiff verfügbar</p>
      ) : null}
      {analysis && <p className="mt-3 rounded-lg border border-emerald-a/20 bg-emerald-a/5 px-3 py-2 text-xs font-semibold leading-relaxed text-fg">Unsere Analyse: {analysis}</p>}
      {metrics && (
        <dl className="mt-3 grid grid-cols-2 gap-2 text-center">
          <div className="rounded-lg bg-surface-2 px-2 py-2"><dt className="text-[11px] text-fg-3">Tore</dt><dd className="mt-1 font-bold tabular-nums text-fg">{metrics.goalsFor}:{metrics.goalsAgainst}</dd></div>
          <div className="rounded-lg bg-surface-2 px-2 py-2"><dt className="text-[11px] text-fg-3">Ø pro Spiel</dt><dd className="mt-1 font-bold tabular-nums text-fg">{metrics.averageFor.toFixed(1)}:{metrics.averageAgainst.toFixed(1)}</dd></div>
          <div className="rounded-lg bg-surface-2 px-2 py-2"><dt className="text-[11px] text-fg-3">Zu null</dt><dd className="mt-1 font-bold tabular-nums text-fg">{metrics.cleanSheets} von {metrics.matches}</dd></div>
          <div className="rounded-lg bg-surface-2 px-2 py-2"><dt className="text-[11px] text-fg-3">Beide treffen</dt><dd className="mt-1 font-bold tabular-nums text-fg">{metrics.bothTeamsScored} von {metrics.matches}</dd></div>
        </dl>
      )}
      <div className="mt-3 rounded-lg border border-line px-3 py-3">
        <p className="text-xs font-bold uppercase tracking-[0.12em] text-fg-2">Spieler in Form</p>
        {playerForm?.status === 'fresh' && playerForm.players.length ? (
          <ol className="mt-2 space-y-2">
            {playerForm.players.map((player) => (
              <li key={player.id || player.name} className="flex items-start justify-between gap-3 text-sm">
                <span className="font-bold text-fg">{player.name}</span>
                <span className="text-right text-fg-2">{playerFormSummary(player)}</span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="mt-2 text-xs leading-relaxed text-fg-2">{playerFormStatusMessage(playerForm)}{leagueScoped && ' Die letzten Ligaspiele werden schrittweise archiviert; fehlende Werte werden nicht geschätzt.'}</p>
        )}
      </div>
      {items.length ? (
        <ul className="mt-3 space-y-2">
          {items.map((item) => <HistoricalMatchRow key={item.fixture_id} item={item} showLineup={showHistoricalLineups} />)}
        </ul>
      ) : (
        <p className="mt-3 text-sm font-semibold text-fg-2">Form nicht verfügbar</p>
      )}
    </section>
  )
}

function HistoricalMatchRow({ item, showLineup = true }: { item: TeamFormMatch; showLineup?: boolean }) {
  const [open, setOpen] = useState(false)
  const history = useMatchHistory(item.fixture_id, open && showLineup)
  const lineups = Object.entries(history.data?.lineups ?? {})
  const hasCompleteLineups = lineups.length >= 2 && lineups.every(([, lineup]) => lineup.starters.length > 0)
  return (
    <li className="rounded-lg bg-surface-2 px-3 py-2.5 text-sm">
      <div className="flex items-center justify-between gap-3">
        <span className="min-w-0 truncate font-semibold text-fg">{item.opponent_name}</span>
        <span className="shrink-0 font-bold tabular-nums text-fg">{item.score}</span>
      </div>
      <div className="mt-1 flex flex-wrap justify-between gap-x-2 text-xs text-fg-2">
        <span>{item.competition_name} · {item.venue === 'home' ? 'Heim' : 'Auswärts'}</span>
        <span>{shortDate(item.played_at)}</span>
      </div>
      {showLineup && <button type="button" onClick={() => setOpen((value) => !value)} className="mt-2 min-h-9 text-xs font-bold text-emerald-a underline underline-offset-4">
        {open ? 'Aufstellung schließen' : 'Aufstellung ansehen'}
      </button>}
      {open && (
        <div className="mt-3 border-t border-line pt-3">
          {history.isLoading ? <p className="text-xs text-fg-2">Aufstellung wird geladen…</p> : history.error ? (
            <div role="alert" className="text-xs text-fg-2">
              <p>Aufstellung konnte nicht geladen werden. Bitte versuche es erneut.</p>
              <button type="button" onClick={() => { void history.refetch() }} disabled={history.isFetching} className="mt-2 min-h-11 font-semibold text-blue-a underline disabled:opacity-50">Aufstellung erneut laden</button>
            </div>
          ) : hasCompleteLineups ? (
            <div className="grid gap-5">
              {lineups.map(([team, lineup]) => <TeamLineup key={team} team={team} lineup={lineup} />)}
            </div>
          ) : <p className="text-xs leading-relaxed text-fg-2">Diese historische Aufstellung ist noch nicht archiviert. Wir ergänzen sie schrittweise, falls der Anbieter sie bereitstellt.</p>}
        </div>
      )}
    </li>
  )
}

function TeamLineup({ team, lineup }: { team: string; lineup: MatchLineup }) {
  const rows = lineupRows(lineup.starters)
  return (
    <div>
      <h3 className="font-display text-xl font-bold text-fg">{team}</h3>
      <p className="mt-1 text-xs text-fg-2">{lineup.formation ? `Formation: ${lineup.formation}` : 'Formation nicht übermittelt'} · Spieler nach Positionsgruppen</p>
      <div className="relative mt-3 min-h-[30rem] overflow-hidden rounded-2xl border-2 border-white/70 bg-emerald-700 px-2 py-5 shadow-inner">
        <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-1/2 border-t-2 border-white/55" />
        <div aria-hidden="true" className="pointer-events-none absolute left-1/2 top-1/2 h-20 w-20 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white/55" />
        <div aria-hidden="true" className="pointer-events-none absolute left-1/2 top-0 h-14 w-36 -translate-x-1/2 border-x-2 border-b-2 border-white/55" />
        <div aria-hidden="true" className="pointer-events-none absolute bottom-0 left-1/2 h-14 w-36 -translate-x-1/2 border-x-2 border-t-2 border-white/55" />
        <ol className="relative z-10 flex min-h-[27.5rem] flex-col justify-around gap-3">
          {rows.map((row) => (
            <li key={row.role}>
              <span className="sr-only">{row.role}</span>
              <ol className="flex items-start justify-around gap-1">
                {row.players.map((player, index) => <PitchPlayer key={player.id || `${player.name}-${index}`} player={player} />)}
              </ol>
            </li>
          ))}
        </ol>
      </div>
      {lineup.substitutes.length > 0 && (
        <details className="mt-3 rounded-xl border border-line px-3 py-2 text-sm text-fg-2">
          <summary className="cursor-pointer font-semibold text-fg">Ersatzbank ({lineup.substitutes.length})</summary>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            {lineup.substitutes.map((player, index) => (
              <li key={player.id || `${player.name}-${index}`} className="flex items-center gap-2 rounded-lg bg-surface-2 px-3 py-2">
                <span className="w-6 text-center font-semibold tabular-nums text-fg-3">{player.jersey || '–'}</span>
                <span className="font-semibold text-fg">{player.name}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

function PitchPlayer({ player }: { player: MatchPlayer }) {
  const surname = player.name.trim().split(/\s+/).at(-1) || player.name
  return (
    <li className="flex min-w-0 max-w-[5.5rem] flex-1 flex-col items-center text-center text-white">
      <span className="flex h-9 w-9 items-center justify-center rounded-full border-2 border-white bg-emerald-950/80 text-xs font-extrabold shadow-md">{player.jersey || '–'}</span>
      <span className="mt-1 rounded-md bg-emerald-950/85 px-1.5 py-0.5 text-[10px] font-bold leading-tight shadow-sm" title={player.name}>{surname}</span>
    </li>
  )
}

export function DetailView() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { competition, setSelectedTeams } = useAppState()
  const isPremierLeague = competition === 'epl2026'
  const isClubCompetition = competition === 'epl2026' || competition === 'ucl2026'
  const [showOddsHistory, setShowOddsHistory] = useState(false)
  const location = useLocation()
  const [view, setView] = useView<MatchView>(MATCH_VIEWS.map((item) => item.value), 'overview')
  const backToGames = () => location.state?.fromFixtureList ? navigate(-((location.state.viewDepth ?? 0) + 1)) : navigate('/')
  const matchQuery = useMatches()
  const { data: matches, isLoading: matchesLoading, error: matchesError, refetch: retryMatches } = matchQuery
  const archive = useArchive()
  const predict = usePredict()
  const loadPrediction = predict.mutate
  const resetPrediction = predict.reset
  const pool = usePoolContext(id)
  const savePool = useSavePoolContext()
  const [copyStatus, setCopyStatus] = useState('')
  const [poolOpen, setPoolOpen] = useState(false)
  const [poolForm, setPoolForm] = useState<PoolForm>(EMPTY_POOL_FORM)
  const [poolStatus, setPoolStatus] = useState('')
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const clock = window.setInterval(() => setNow(Date.now()), 15_000)
    return () => window.clearInterval(clock)
  }, [])

  const match: Match | undefined = useMemo(() => matches?.find((item) => item.id === id), [matches, id])
  const isClubMatchUpcoming = Boolean(isClubCompetition && match && fixtureStatus(match, now) === 'upcoming')
  const predictionInput = useMemo(() => {
    if (!match?.raw_match) return undefined
    return {
      targetCompetition: competition,
      match: {
        ...match.raw_match,
        match_context: match.match_context ?? match.context,
        stage: match.stage,
        tie_id: match.tie_id,
        leg: match.leg,
        first_leg_score: match.first_leg_score,
        extra_time_eligible: match.extra_time_eligible,
        is_ko_phase: match.is_ko_phase,
      },
    }
  }, [competition, match])

  useEffect(() => {
    if (!isClubCompetition) {
      if (predictionInput) loadPrediction(predictionInput)
      return
    }
    resetPrediction()
    if (predictionInput && isClubMatchUpcoming) loadPrediction(predictionInput)
    return () => resetPrediction()
  }, [isClubCompetition, isClubMatchUpcoming, loadPrediction, predictionInput, resetPrediction])

  useEffect(() => {
    if (!pool.data) return
    setPoolForm({
      user_points: String(pool.data.user_points),
      leader_points: String(pool.data.leader_points),
      remaining_srf_max_points: String(pool.data.remaining_srf_max_points),
      tipRows: [
        ...Object.entries(pool.data.tip_counts ?? {}).map(([tip, count]) => ({ tip, count: String(count) })),
        { tip: '', count: '' },
      ],
    })
  }, [pool.data])

  if (!matches && matchesError) {
    return <PageTransition><QueryState title="Spiele konnten nicht geladen werden" message="Die Spielinformationen sind gerade nicht erreichbar. Bitte versuche es erneut." onRetry={() => { void retryMatches() }} /></PageTransition>
  }
  if (!matches && matchesLoading) {
    return <PageTransition><div className="space-y-4"><Skeleton className="h-8 w-40" /><ChartSkeleton /><Skeleton className="h-32 w-full" /></div></PageTransition>
  }
  if (!matches) {
    return <PageTransition><QueryState title="Spiele sind nicht verfügbar" message="Es liegen keine geladenen Spielinformationen vor." onRetry={() => { void retryMatches() }} /></PageTransition>
  }
  if (!match) {
    return (
      <PageTransition>
        <button type="button" onClick={backToGames} className="mb-2 min-h-11 text-sm font-semibold text-blue-a hover:underline">← Zurück zur Übersicht</button>
        <QueryState title="Spiel nicht gefunden" message="Dieses Spiel ist in der aktuellen Spielliste nicht enthalten. Kehre zur Übersicht zurück und wähle ein anderes Spiel." />
      </PageTransition>
    )
  }

  const kickoff = match.raw_match?.commence_time
  const hasKickoff = Boolean(kickoff && Number.isFinite(Date.parse(kickoff)))
  const kickoffLabel = hasKickoff ? `${shortDate(kickoff)} · ${kickoffTime(kickoff)}` : 'Anstoßzeit nicht verfügbar'
  const requestMatchesCurrentMatch = predict.variables?.targetCompetition === competition && predict.variables?.match.id === match.id
  const currentPrediction = requestMatchesCurrentMatch ? predict.data : undefined
  const fixtureState = fixtureStatus(match, now)
  const isUpcoming = fixtureState === 'upcoming'
  const archivedClubPrediction = isClubCompetition && !isUpcoming ? archive.data?.[match.id]?.prediction : undefined
  const clubPrediction = isClubCompetition ? (isUpcoming ? currentPrediction : archivedClubPrediction) : undefined
  const selectedPrediction = isClubCompetition ? clubPrediction : predict.data
  const predictionIsPending = isClubCompetition ? isUpcoming && requestMatchesCurrentMatch && predict.isPending : predict.isPending
  const predictionHasError = isClubCompetition ? isUpcoming && requestMatchesCurrentMatch && predict.isError : predict.isError
  const predictionIsSuccess = isClubCompetition ? isUpcoming && requestMatchesCurrentMatch && predict.isSuccess : predict.isSuccess
  const canRetryPrediction = Boolean(predictionInput && (!isClubCompetition || isUpcoming))
  const cachedModelTip = isClubCompetition && !isUpcoming
    ? archivedClubPrediction?.model_tip ?? archivedClubPrediction?.top_tip ?? null
    : match.model_tip ?? match.top_tip
  const predictionTip = selectedPrediction?.model_tip ?? selectedPrediction?.top_tip ?? null
  const modelTip = predictionTip ?? cachedModelTip
  const activeTip = modelTip && modelTip !== 'N/A' ? modelTip : null
  const canCopy = isUpcoming && Boolean(activeTip)
  const hasBookmakerOdds = Boolean(match.odds && [match.odds.home, match.odds.draw, match.odds.away].every((price) => Number.isFinite(price) && price > 1))
  const displayedPrediction = isClubCompetition
    ? clubPrediction ?? (isUpcoming ? match : undefined)
    : predict.data?.probabilities != null || predictionTip != null ? predict.data : match
  const displayedProbabilities = displayedPrediction?.probabilities ?? null
  const outcomeSource = outcomeSourceLabel(displayedPrediction?.source_mode, displayedPrediction?.source)
  const outcomeObservedAt = displayedPrediction?.observed_at ?? (displayedPrediction === match ? match.odds_observed_at : null)
  const marketProbabilities = hasBookmakerOdds ? computeImpliedProbs(match.odds) : null
  const tipInsights = rankedTipInsights(selectedPrediction?.xp_tips, selectedPrediction?.matrix)
  const recommendedInsight = tipInsights.find(item => item.tip === activeTip)
  const expectedPoints = predictionTip != null ? (recommendedInsight?.expectedPoints ?? selectedPrediction?.max_xp) : (isClubCompetition && !isUpcoming ? archivedClubPrediction?.max_xp : match.max_xp)
  const xgHome = isClubCompetition && !isUpcoming ? null : (selectedPrediction?.xg_home ?? match.xg_home)
  const xgAway = isClubCompetition && !isUpcoming ? null : (selectedPrediction?.xg_away ?? match.xg_away)
  const xgTotal = (xgHome ?? 0) + (xgAway ?? 0)
  const missing = Object.entries(match.lineup_diff ?? {}).filter(([, value]) => value.missing?.length)
  const lineup = lineupState(match.match_intelligence, match.home_team, match.away_team)
  const stage = isPremierLeague ? 'Premier League' : stageLabel(match.stage)

  const copyTip = async () => {
    if (!activeTip) return
    try {
      await navigator.clipboard.writeText(activeTip)
      setCopyStatus('Der Modelltipp wurde in die Zwischenablage kopiert. Er wird dadurch nicht gespeichert.')
    } catch {
      setCopyStatus('Kopieren war nicht möglich. Du kannst den Modelltipp markieren und manuell kopieren.')
    }
  }

  const savePoolContext = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const userPoints = Number(poolForm.user_points)
    const leaderPoints = Number(poolForm.leader_points)
    const remainingPoints = Number(poolForm.remaining_srf_max_points)
    const tipCounts = parseTipCountRows(poolForm.tipRows)
    if (!Number.isInteger(userPoints) || userPoints < 0 || !Number.isInteger(leaderPoints) || leaderPoints < 0 || !Number.isInteger(remainingPoints) || remainingPoints < 1) {
      setPoolStatus('Punkte müssen ganze Zahlen sein. Die noch möglichen Punkte müssen mindestens 1 betragen.')
      return
    }
    if (!tipCounts) {
      setPoolStatus('Jede angegebene Zeile braucht ein Ergebnis im Format 1:0 und eine ganze, nicht negative Anzahl.')
      return
    }

    setPoolStatus('Speichert …')
    savePool.mutate({
      matchId: match.id,
      context: {
        user_points: userPoints,
        leader_points: leaderPoints,
        remaining_srf_max_points: remainingPoints,
        tip_counts: tipCounts,
      },
    }, {
      onSuccess: () => setPoolStatus('Pool-Kontext für dieses Spiel gespeichert.'),
      onError: (error) => setPoolStatus(requestErrorMessage(error)),
    })
  }

  return (
    <PageTransition>
      <div className="detail-actions">
        <button type="button" onClick={backToGames} className="min-h-11 text-sm font-semibold text-blue-a hover:underline">← Zurück zur Übersicht</button>
        <button type="button" aria-label="Diese Teams vergleichen" onClick={() => { setSelectedTeams([match.home_team, match.away_team]); navigate('/team-form') }} className="min-h-11 text-xs font-semibold text-blue-a hover:underline">Teams vergleichen</button>
      </div>
      {matchesError && <div className="mb-4"><QueryState title="Spiele konnten nicht aktualisiert werden" message="Die zuletzt geladenen Spielinformationen werden angezeigt. Prüfe die Verbindung und lade die Liste erneut." onRetry={() => { void retryMatches() }} /></div>}

      <header className="page-header match-heading">
        <p className="page-description">{stage}{match.is_ko_phase ? ' · K.-o.-Phase' : ''} · {kickoffLabel} · {matchStatusLabel(match, now)}</p>
        <h1 className="page-title mt-3 grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 text-xl tracking-tight sm:gap-5 sm:text-3xl">
          <span className="flex min-w-0 items-center gap-2"><TeamLogo name={match.home_team} src={match.home_logo} className="h-7 w-7 sm:h-9 sm:w-9" /><span className="min-w-0 break-words">{match.home_team}</span></span>
          <span className="text-xs font-medium text-fg-3 sm:text-sm">gegen</span>
          <span className="flex min-w-0 items-center justify-end gap-2 text-right"><span className="min-w-0 break-words">{match.away_team}</span><TeamLogo name={match.away_team} src={match.away_logo} className="h-7 w-7 sm:h-9 sm:w-9" /></span>
        </h1>
      </header>

      <ViewTabs id="match-analysis" label="Spielanalyse" items={MATCH_VIEWS} value={view} onChange={setView} wrap={isClubCompetition} />

      <ViewPanel id="match-analysis" value="overview" active={view}>
        <div className="match-grid">
          <section className="match-card match-card-recommendation" aria-labelledby="recommendation-title">
            <div className="section-heading">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-a">Empfehlung</p>
                <h2 id="recommendation-title" className="mt-1 text-lg font-bold text-fg" aria-label="Empfohlener Ergebnistipp">Modelltipp</h2>
              </div>
              <MatchDataStatus match={match} prediction={predictionTip != null ? selectedPrediction : undefined} now={now} badge />
            </div>
            <div className="mt-3 flex items-center justify-between gap-4">
              <p className="display-num text-4xl text-fg">{activeTip ?? '–'}</p>
              <button type="button" onClick={() => { void copyTip() }} disabled={!canCopy} className="copy-tip-button max-w-44">Tipp kopieren <span aria-hidden="true">↗</span></button>
            </div>
            {copyStatus && <p role="status" className="mt-2 text-xs text-fg-2">{copyStatus}</p>}
            {predictionIsPending && <p role="status" className="mt-3 text-xs text-fg-3">Die Spielanalyse wird aktualisiert. Der vorhandene Spieltipp bleibt sichtbar.</p>}
            {predictionHasError && <div className="mt-3 rounded-lg border border-line bg-surface-2 p-3 text-sm text-fg-2" role="alert">
              <p>Die Aktualisierung der Spielanalyse ist fehlgeschlagen{activeTip ? '; der vorhandene Spieltipp wird weiterhin angezeigt.' : '.'}</p>
              {canRetryPrediction && predictionInput && <button type="button" onClick={() => predict.mutate(predictionInput)} className="mt-2 min-h-11 font-semibold text-blue-a underline">Analyse erneut laden</button>}
            </div>}
            {predictionIsSuccess && !selectedPrediction?.model_tip && !selectedPrediction?.top_tip && !activeTip && <p className="mt-3 text-sm text-fg-2">Für dieses Spiel ist keine Ergebnismitteilung verfügbar.</p>}
          </section>

          <section className="match-card match-card-tip" aria-label="Gemeinsamer Spieltipp">
            {archive.isLoading && <p role="status" className="rounded-lg border border-line p-4 text-sm text-fg-2">Gespeicherte gemeinsame Tipps werden geladen …</p>}
            {archive.error && <div role="alert" className="rounded-lg border border-line p-4 text-sm text-fg-2">
              <h2 className="font-semibold text-fg">Gemeinsame Tipps konnten nicht geladen werden</h2>
              <p className="mt-1">Lade die gespeicherten Tipps erneut, bevor du einen Tipp abgibst.</p>
              <button type="button" onClick={() => { void archive.refetch() }} disabled={archive.isFetching} className="mt-2 min-h-11 font-semibold text-blue-a underline disabled:opacity-50">Tipps erneut laden</button>
            </div>}
            {archive.data && <SharedTipEditor key={`${competition}:${match.id}`} match={match} competition={competition} savedTip={archive.data[match.id]?.prediction?.user_tip} now={now} unavailableReason={archive.error ? 'Tipps sind gerade nicht erreichbar. Deine Eingabe bleibt erhalten.' : undefined} />}
          </section>
        </div>

        <div className="match-grid analysis-section">
          <section className="surface-panel" aria-labelledby="outcome-title">
            <div className="section-heading">
              <div><h2 id="outcome-title" className="text-base font-bold text-fg">{isClubCompetition ? 'Sieg, Remis, Niederlage nach 90 Minuten' : 'Sieg, Remis, Niederlage'}</h2><p className="mt-1 text-xs text-fg-3">Einschätzung für den Spielausgang</p></div>
            </div>
            <OutcomeBar probabilities={displayedProbabilities} homeTeam={match.home_team} awayTeam={match.away_team} sourceLabel={outcomeSource} observedAt={outcomeObservedAt} compact basisLabel={isClubCompetition ? 'Nach 90 Minuten' : undefined} />
          </section>
          <MatchDataStatus match={match} prediction={predictionTip != null ? selectedPrediction : undefined} now={now} />
        </div>
      </ViewPanel>

      <ViewPanel id="match-analysis" value="form" active={view}>
        <section className="analysis-section match-card" aria-labelledby="form-title">
          <div className="section-heading"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-a">Teamleistung</p><h2 id="form-title" className="mt-1 text-lg font-bold text-fg">Tore & Form</h2></div></div>
          {xgHome != null && xgAway != null && xgTotal > 0 ? (
            <div className="metric-strip mt-4">
              {[
                { team: match.home_team, xg: xgHome, form: match.home_form },
                { team: match.away_team, xg: xgAway, form: match.away_form },
              ].map(({ team, xg, form }) => (
                <div key={team} className="surface-panel">
                  <div className="flex items-center justify-between gap-2 text-sm font-medium text-fg"><span>{team}</span><span className="display-num text-2xl">{xg.toFixed(2)} <span className="text-xs font-normal text-fg-3">xG</span></span></div>
                  <div className="chance-track mt-2"><div className="chance-fill" style={{ width: `${(xg / xgTotal) * 100}%` }} /></div>
                  {!isClubCompetition && <div className="mt-3" aria-label={`${team}: ${recentFormSummary(form)}`}><FormBadges form={form} /></div>}
                  {form?.status === 'stale' && <p className="mt-2 text-xs text-amber-a">Älterer Formstand</p>}
                  {form?.status === 'unavailable' && <p className="mt-2 text-xs text-fg-3">Formdaten nicht verfügbar.</p>}
                </div>
              ))}
              <p className="text-xs text-fg-3">xG = erwartete Tore im Modellschnitt</p>
            </div>
          ) : <p className="mt-3 text-sm text-fg-2">Torprognose nicht verfügbar.</p>}
        </section>

        <section className="analysis-section match-card" aria-labelledby="history-title">
          <div className="section-heading"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-a">Vergangene Spiele</p><h2 id="history-title" className="mt-1 text-lg font-bold text-fg">Letzte Pflichtspiele</h2></div></div>
          {!isClubCompetition && <p className="mt-2 text-xs text-fg-3">{match.home_form?.scope === 'league' || match.away_form?.scope === 'league' ? 'Die Form umfasst zuletzt erfasste Premier-League-Spiele, keine anderen Wettbewerbe.' : 'Die Form umfasst zuletzt erfasste Pflichtspiele aller Wettbewerbe.'}</p>}
          <div className="match-grid mt-4">
            {[{ team: match.home_team, form: match.home_form }, { team: match.away_team, form: match.away_form }].map(({ team, form }) => (
              isClubCompetition
                ? <ClubTeamFormHistory key={team} team={team} form={form} beforeKickoff={kickoff ?? null} />
                : <section key={team} className="surface-panel">
                  <div className="flex items-center gap-2 text-sm font-bold text-fg"><TeamLogo name={team} />{team}</div>
                  <div className="mt-2"><FormBadges form={form} /></div>
                  <TeamFormHistory team={team} form={form} kickoff={kickoff} showHistoricalLineups={false} />
                </section>
            ))}
          </div>
        </section>
      </ViewPanel>

      <ViewPanel id="match-analysis" value="lineups" active={view}>
        {missing.length > 0 && <section className="analysis-section match-card" aria-labelledby="missing-title">
          <div className="section-heading"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-amber-a">Kaderhinweis</p><h2 id="missing-title" className="mt-1 text-lg font-bold text-fg">Fehlende Spieler in der Aufstellung</h2></div></div>
          {missing.map(([team, value]) => <p key={team} className="mt-2 text-sm text-fg-2"><b className="text-fg">{team}:</b> {value.missing.join(', ')}</p>)}
        </section>}

        <GlassCard className="analysis-section match-card match-card-lineup">
          <div className="section-heading">
            <div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-a">Kurz vor Anpfiff</p><SectionTitle className="mt-1 text-lg">Aufstellungen & Spieler</SectionTitle></div>
            {lineup.kind === 'confirmed' && <span className="rounded-full bg-emerald-a/10 px-3 py-1 text-xs font-bold text-emerald-a">Bestätigt · {lineup.source === 'api_football' ? 'API-Football' : 'ESPN'}</span>}
          </div>
          {lineup.kind === 'confirmed' ? (
            <div className="mt-5 grid gap-7 lg:grid-cols-2">
              <TeamLineup team={match.home_team} lineup={lineup.home} />
              <TeamLineup team={match.away_team} lineup={lineup.away} />
            </div>
          ) : (
            <div className="mt-4 rounded-xl bg-surface-2 px-4 py-4">
              <p className="font-semibold text-fg">{lineup.message}</p>
              <p className="mt-1 text-sm leading-relaxed text-fg-2">{isPremierLeague ? 'Der Wartungslauf prüft ESPN etwa 35 und 15 Minuten vor dem Anpfiff, sofern Aufstellungen verfügbar sind. Diese Seite liest nur gespeicherte Daten.' : 'Wir prüfen automatisch etwa 35 und 15 Minuten vor dem Anpfiff. Bis dahin entstehen keine zusätzlichen API-Abfragen beim Öffnen dieser Seite.'}</p>
            </div>
          )}
          {isClubCompetition && (!match.match_intelligence?.injuries || match.match_intelligence.injuries.status !== 'fresh') && <p className="mt-4 text-xs text-fg-3">Keine verlässlichen Verletzungsdaten für dieses Spiel erfasst; daraus lässt sich nicht ableiten, ob Spieler fehlen.</p>}
          {missing.length === 0 && !isClubCompetition && <p className="mt-4 text-xs text-fg-3">Keine fehlenden Spieler für diese Aufstellung erfasst.</p>}
          {missing.length === 0 && isClubCompetition && lineup.kind === 'confirmed' && <p className="mt-4 text-xs text-fg-3">In den bestätigten Aufstellungen sind keine Spieler als fehlend markiert. Das ersetzt keine vollständigen Verletzungsdaten.</p>}
        </GlassCard>

        <section className="analysis-section match-card" aria-labelledby="historical-lineups-title">
          <div className="section-heading"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-a">Archiv</p><h2 id="historical-lineups-title" className="mt-1 text-lg font-bold text-fg">Historische Aufstellungen</h2></div></div>
          <div className="match-grid mt-4">
            {[{ team: match.home_team, form: match.home_form }, { team: match.away_team, form: match.away_form }].map(({ team, form }) => {
              const history = (isClubCompetition ? verifiedClubFormMatches(form, { before: kickoff ?? null }) : form?.matches ?? []).slice(0, 10)
              return <section key={team} className="surface-panel"><h3 className="font-bold text-fg">{team}</h3>
                {history.length ? <ul className="mt-3 space-y-2">{history.map((item) => <HistoricalMatchRow key={item.fixture_id} item={item} />)}</ul> : <p className="mt-2 text-sm text-fg-2">Keine vergangenen Spiele für historische Aufstellungen verfügbar.</p>}
              </section>
            })}
          </div>
        </section>
      </ViewPanel>

      <ViewPanel id="match-analysis" value="market" active={view}>
        <section className="analysis-section match-card" aria-labelledby="market-title">
          <div className="section-heading"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-a">Buchmacher</p><h2 id="market-title" className="mt-1 text-lg font-bold text-fg">Aktuelle Quoten</h2></div></div>
          {hasBookmakerOdds && marketProbabilities ? <>
            <p className="mt-2 text-sm text-fg-2">Dezimalquoten für Sieg, Remis und Sieg. Die danebenstehenden Chancen werden aus diesen drei Quoten normalisiert und sind keine Modellprognose.</p>
            <p className="mt-2 text-xs text-fg-3">Quelle: {match.odds_provenance?.source === 'odds_api' ? 'The Odds API' : String(match.odds_provenance?.source ?? 'Quelle nicht belegt')} · {match.odds_observed_at ? formatObservedAt(match.odds_observed_at) : 'Zeitpunkt nicht verfügbar'}</p>
            <div className="ranking-list mt-4">
              {[
                { key: 'home', label: `${match.home_team} gewinnt` },
                { key: 'draw', label: 'Unentschieden' },
                { key: 'away', label: `${match.away_team} gewinnt` },
              ].map(({ key, label }) => {
                const price = match.odds?.[key as 'home' | 'draw' | 'away']
                const probability = marketProbabilities[key as 'home' | 'draw' | 'away']
                return <div key={key} className="ranking-row">
                  <span className="font-semibold text-fg">{label}</span>
                  <span className="text-right"><b className="block tabular-nums text-fg">{price?.toFixed(2) ?? '–'}</b><span className="text-xs text-fg-3">{pct(probability)} implizit</span></span>
                </div>
              })}
            </div>
          </> : <p className="mt-3 rounded-lg bg-surface-2 p-4 text-sm text-fg-2">Für dieses Spiel sind keine aktuellen Buchmacherquoten verfügbar.</p>}
        </section>

        <details className="analysis-section match-card rounded-2xl border border-line bg-surface px-5 py-4" onToggle={(event) => setShowOddsHistory(event.currentTarget.open)}>
          <summary className="min-h-11 cursor-pointer text-sm font-bold text-fg">Wie haben sich die Quoten verändert?</summary>
          <OddsHistory matchId={match.id} homeTeam={match.home_team} awayTeam={match.away_team} enabled={showOddsHistory} />
        </details>
      </ViewPanel>

      <ViewPanel id="match-analysis" value="model" active={view}>
        <section className="analysis-section match-card" aria-labelledby="model-title">
          <div className="section-heading"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-a">Ergebnismodell</p><h2 id="model-title" className="mt-1 text-lg font-bold text-fg">Ergebnis-Alternativen</h2></div></div>
          <p className="mt-2 text-xs text-fg-3">Nach erwarteten Tippspielpunkten. Die Chance für den exakten Treffer ist davon getrennt.</p>
          {activeTip && <div className="metric-strip mt-4">
            <div className="surface-panel"><span className="block text-xs text-fg-3">Modelltipp</span><strong className="mt-1 block display-num text-2xl text-fg">{activeTip}</strong></div>
            <div className="surface-panel"><span className="block text-xs text-fg-3">Ø erwartete Punkte</span><strong className="mt-1 block display-num text-2xl text-fg">{expectedPoints != null && Number.isFinite(expectedPoints) ? expectedPoints.toFixed(2) : '–'}</strong></div>
            <div className="surface-panel"><span className="block text-xs text-fg-3">Exakte Trefferchance</span><strong className="mt-1 block display-num text-2xl text-fg">{recommendedInsight?.exactChance != null ? pct(recommendedInsight.exactChance) : '–'}</strong></div>
          </div>}
          {tipInsights.length ? <ol className="ranking-list mt-4">{tipInsights.map((item, index) => (
            <li key={item.tip} className="ranking-row"><span className="flex items-center gap-3"><b className="display-num text-xl text-fg">{item.tip}</b>{index === 0 && <span className="rounded-full bg-blue-a/10 px-2 py-1 text-xs font-medium text-blue-a">Empfehlung</span>}</span><span className="text-right"><b className="block tabular-nums text-fg">{item.expectedPoints.toFixed(2)} Punkte</b><span className="text-xs tabular-nums text-fg-3">{item.exactChance === null ? 'Trefferchance nicht verfügbar' : `${(item.exactChance * 100).toFixed(1)} % genau`}</span></span></li>
          ))}</ol> : <p className="mt-4 text-sm text-fg-2">{predictionHasError ? 'Die Ergebnistipps konnten nicht berechnet werden.' : predictionIsPending ? 'Die Ergebnistipps werden berechnet.' : 'Für dieses Spiel liegen keine weiteren Ergebnistipps vor.'}</p>}
        </section>

        <div className="match-grid analysis-section">
          <section className="match-card" aria-labelledby="matrix-title"><div className="section-heading"><div><h2 id="matrix-title" className="text-base font-bold text-fg">Wahrscheinlichkeit je Ergebnis</h2><p className="mt-1 text-xs text-fg-3">{isClubCompetition ? 'Heimtore (Zeilen) · Auswärtstore (Spalten)' : 'Einzelne Spielstände laut Score-Matrix'}</p></div></div><div className="mt-4">{selectedPrediction?.matrix ? <ScoreHeatmap modelTip={activeTip} calc={selectedPrediction} homeDisp={match.home_disp || match.home_team} awayDisp={match.away_disp || match.away_team} /> : <p className="text-sm text-fg-2">Für die Ergebnistabelle sind keine Daten verfügbar.</p>}</div></section>
          <section className="match-card" aria-labelledby="other-tips-title"><div className="section-heading"><div><h2 id="other-tips-title" className="text-base font-bold text-fg">Weitere Modelltipps</h2><p className="mt-1 text-xs text-fg-3">Alternative Vorschläge nach erwarteten Punkten</p></div></div>
            {selectedPrediction?.xp_tips?.length ? <ol className="ranking-list mt-3">{selectedPrediction.xp_tips.slice(0, 5).map((item, index) => <li key={item.Tipp} className="ranking-row"><span className="text-fg-2">{index + 1}. <b className="ml-1 display-num text-lg text-fg">{item.Tipp}</b></span><span className="tabular-nums text-fg-2">{item.xP.toFixed(2)} erwartete Punkte</span></li>)}</ol> : <p className="mt-3 text-sm text-fg-2">Keine weiteren Modelltipps verfügbar.</p>}
          </section>
          {match.bots && Object.keys(match.bots).length > 0 && <section className="match-card"><div className="section-heading"><h2 className="text-base font-bold text-fg">Bot-Vorschläge</h2></div><ul className="ranking-list mt-3">{(Object.keys(BOT_LABELS) as BotKey[]).map((key) => {
            const tip = match.bots?.[key]?.tip
            return tip ? <li key={key} className="ranking-row"><span className="text-fg-2">{BOT_LABELS[key]}</span><b className="display-num text-fg">{tip}</b></li> : null
          })}</ul></section>}
        </div>

        <section className="analysis-section match-card"><div className="section-heading"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-a">Zusätzlicher Kontext</p><h2 className="mt-1 text-lg font-bold text-fg">Spielhinweise</h2></div></div><div className="mt-3"><MatchHintCard match={match} competition={competition} /></div></section>

        <section className="analysis-section match-card" aria-labelledby="pool-context-title">
          <h2 id="pool-context-title" className="sr-only">Pool-Tipp und Rundendaten</h2>
          <PoolContextEditor pool={pool} form={poolForm} onFormChange={setPoolForm} open={poolOpen} onToggle={() => setPoolOpen((current) => !current)} status={poolStatus} onSave={savePoolContext} saving={savePool.isPending} />
        </section>

        <details className="analysis-section match-card info-disclosure">
          <summary>Wie wird der Tipp gewählt?</summary>
          <div className="info-content"><p>Das Modell wählt den Ergebnistipp mit den höchsten erwarteten Tippspielpunkten. Erwartete Punkte sind der Durchschnitt über mögliche Ergebnisse. Torwerte beschreiben einen Modellschnitt und sind kein garantiertes Ergebnis.</p><p className="mt-2">Kopieren überträgt den Vorschlag nur in die Zwischenablage. Speichern legt einen gemeinsamen Tipp für das Spiel ab: nicht nutzergetrennt und für alle sichtbar. Die Abgabe schließt fünf Minuten vor Anpfiff.</p></div>
        </details>
      </ViewPanel>
    </PageTransition>
  )
}

function PoolContextEditor({
  pool, form, onFormChange, open, onToggle, status, onSave, saving,
}: {
  pool: ReturnType<typeof usePoolContext>
  form: PoolForm
  onFormChange: (form: PoolForm) => void
  open: boolean
  onToggle: () => void
  status: string
  onSave: (event: FormEvent<HTMLFormElement>) => void
  saving: boolean
}) {
  const poolTip = pool.data?.pool_tip
  return (
    <section className="rounded-xl border border-line p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-fg">Pool-Tipp und Rundendaten</h3>
          <p className="mt-1 text-sm text-fg-2">Optionaler Kontext aus deiner Tipprunde für dieses Spiel.</p>
        </div>
        <button type="button" onClick={onToggle} className="min-h-11 rounded-lg border border-line-2 px-3 text-sm font-medium text-fg hover:bg-surface-2">{open ? 'Schliessen' : 'Daten eingeben'}</button>
      </div>

      {pool.isLoading && <p role="status" className="mt-3 text-sm text-fg-2">Pool-Kontext wird geladen.</p>}
      {pool.error && <div className="mt-3"><QueryState title="Pool-Kontext nicht geladen" message="Die gespeicherten Rundendaten sind nicht erreichbar. Du kannst es erneut versuchen oder neue Angaben eingeben." onRetry={() => { void pool.refetch() }} /></div>}
      {!pool.isLoading && !pool.error && <p className="mt-3 text-sm text-fg-2">{poolTip ? <>Vorschlag der Tipprunde: <b className="tabular-nums text-fg">{poolTip}</b></> : 'Kein Pool-Tipp verfügbar. Für diesen Vorschlag braucht es die Punktestände und die Verteilung der abgegebenen Tipps.'}</p>}

      {open && (
        <form onSubmit={onSave} className="mt-4 space-y-4 border-t border-line pt-4">
          <p className="text-xs leading-relaxed text-fg-3">Diese optionalen Angaben werden zentral für dieses Spiel gespeichert. Trage die Werte aus deiner Runde ein; die Tippverteilung darf leer bleiben.</p>
          <div className="grid gap-3 sm:grid-cols-3">
            <PoolNumberField label="Deine bisherigen Punkte" value={form.user_points} min={0} onChange={(value) => onFormChange({ ...form, user_points: value })} />
            <PoolNumberField label="Punkte der führenden Person" value={form.leader_points} min={0} onChange={(value) => onFormChange({ ...form, leader_points: value })} />
            <PoolNumberField label="Für dich noch mögliche Punkte" value={form.remaining_srf_max_points} min={1} onChange={(value) => onFormChange({ ...form, remaining_srf_max_points: value })} />
          </div>
          <fieldset>
            <legend className="text-sm font-medium text-fg">Abgegebene Tipps nach Ergebnis (optional)</legend>
            <p className="mt-1 text-xs text-fg-3">Ergebnis und Anzahl pro Zeile, zum Beispiel 1:0 und 4 Tipps.</p>
            <div className="mt-2 space-y-2">
              {form.tipRows.map((row, index) => (
                <div key={index} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-2">
                  <label className="text-xs text-fg-2">Ergebnis
                    <input type="text" value={row.tip} onChange={(event) => updatePoolTipRow(form, onFormChange, index, 'tip', event.target.value)} placeholder="z. B. 1:0" className="mt-1 min-h-11 w-full rounded-lg border border-line-2 bg-surface px-3 text-sm text-fg outline-none placeholder:text-fg-3 focus:border-blue-a" />
                  </label>
                  <label className="text-xs text-fg-2">Anzahl der Tipps
                    <input type="number" min={0} step={1} value={row.count} onChange={(event) => updatePoolTipRow(form, onFormChange, index, 'count', event.target.value)} className="mt-1 min-h-11 w-full rounded-lg border border-line-2 bg-surface px-3 text-sm tabular-nums text-fg outline-none focus:border-blue-a" />
                  </label>
                </div>
              ))}
            </div>
            <button type="button" onClick={() => onFormChange({ ...form, tipRows: [...form.tipRows, { tip: '', count: '' }] })} className="mt-2 min-h-11 text-sm font-medium text-blue-a hover:underline">+ Ergebnis hinzufügen</button>
          </fieldset>
          <div className="flex flex-wrap items-center gap-3">
            <button type="submit" disabled={saving} className="min-h-11 rounded-lg bg-action px-4 text-sm font-semibold text-on-action hover:opacity-90 disabled:opacity-50">{saving ? 'Speichert …' : 'Rundendaten speichern'}</button>
            <span className="text-sm text-fg-2" role="status">{status}</span>
          </div>
        </form>
      )}
    </section>
  )
}

function updatePoolTipRow(form: PoolForm, onChange: (form: PoolForm) => void, index: number, field: keyof TipCountRow, value: string) {
  onChange({
    ...form,
    tipRows: form.tipRows.map((row, rowIndex) => rowIndex === index ? { ...row, [field]: value } : row),
  })
}

function PoolNumberField({ label, value, min, onChange }: { label: string; value: string; min: number; onChange: (value: string) => void }) {
  return (
    <label className="text-xs font-medium text-fg-2">
      {label}
      <input required type="number" min={min} step={1} value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 min-h-11 w-full rounded-lg border border-line-2 bg-surface px-3 text-sm tabular-nums text-fg outline-none focus:border-blue-a focus:ring-2 focus:ring-blue-a/20" />
    </label>
  )
}
