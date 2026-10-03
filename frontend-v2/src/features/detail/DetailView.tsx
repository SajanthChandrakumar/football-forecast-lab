import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { useArchive, useMatches, usePoolContext, usePredict, useSavePoolContext } from '../../hooks/queries'
import { useAppState } from '../../state/AppState'
import { computeImpliedProbs, pct } from '../../lib/util'
import { kickoffTime, shortDate } from '../../lib/format'
import { fixtureStatus } from '../../lib/fixture-status.mjs'
import type { BotKey, Match, TeamForm } from '../../lib/types'
import { FormBadges, TeamLogo } from '../../components/shared/Badges'
import { MatchHintCard } from '../../components/shared/MatchHintCard'
import { SharedTipEditor } from '../../components/shared/SharedTipEditor'
import { PageTransition } from '../../components/shared/PageTransition'
import { QueryState } from '../../components/shared/QueryState'
import { ChartSkeleton, Skeleton } from '../../components/shared/Skeleton'
import { ScoreHeatmap } from './ScoreHeatmap'
import { formatDataStatus, formatObservedAt, parseTipCountRows } from './detail-form.mjs'
import type { TipCountRow } from './detail-form.mjs'
import { rankedTipInsights, recentFormSummary, matchLoadSummary } from '../../lib/tip-insights.mjs'

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

const sourceLabels: Record<string, string> = {
  api_football: 'API-Football',
  clubelo: 'ClubElo',
  elo: 'Elo-Modell',
  espn: 'ESPN',
  'espn+fotmob': 'ESPN + FotMob',
  fotmob: 'FotMob',
  market: 'Marktdaten',
  odds_api: 'The Odds API',
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

function sourceLabel(source?: string | null) {
  if (!source || source === 'none') return 'Quelle nicht angegeben'
  if (sourceLabels[source]) return sourceLabels[source]
  return source.split('+').map((part) => sourceLabels[part] ?? part.replaceAll('_', ' ')).join(' + ')
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

function TeamFormHistory({ team, form, kickoff }: { team: string; form?: TeamForm; kickoff?: string }) {
  if (!form?.status && !form?.matches?.length) return null
  const items = form?.matches?.slice(0, 5) ?? []
  const source = form?.source ? sourceLabel(form.source) : null
  const load = matchLoadSummary(form, kickoff)

  return (
    <section className="rounded-xl border border-line bg-surface p-4">
      <h3 className="text-base font-semibold text-fg">{team}</h3>
      <p className="mt-1 text-xs text-fg-2">Letzte Pflichtspiele über alle Wettbewerbe{source ? ` · Quelle: ${source}` : ''}</p>
      {form?.status === 'stale' && <p className="mt-2 text-xs font-medium text-amber-a">Der Datenstand kann veraltet sein.</p>}
      {load && <p className="mt-3 rounded-lg bg-surface-2 px-3 py-2 text-xs text-fg-2">{load}</p>}
      {items.length ? (
        <ul className="mt-3 space-y-2">
          {items.map((item) => (
            <li key={item.fixture_id} className="rounded-lg bg-surface-2 px-3 py-2.5 text-sm">
              <div className="flex items-center justify-between gap-3">
                <span className="min-w-0 truncate font-medium text-fg">{item.opponent_name}</span>
                <span className="shrink-0 font-semibold tabular-nums text-fg">{item.score}</span>
              </div>
              <div className="mt-1 flex flex-wrap justify-between gap-x-2 text-xs text-fg-2">
                <span>{item.competition_name} · {item.venue === 'home' ? 'Heim' : 'Auswärts'}</span>
                <span>{shortDate(item.played_at)}</span>
              </div>
            </li>
          ))}
        </ul>
      ) : <p className="mt-3 text-sm text-fg-2">Form nicht verfügbar.</p>}
    </section>
  )
}

export function DetailView() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { competition, setSelectedTeams } = useAppState()
  const location = useLocation()
  const backToGames = () => location.state?.fromFixtureList ? navigate(-1) : navigate('/')
  const matchQuery = useMatches()
  const { data: matches, isLoading: matchesLoading, error: matchesError, refetch: retryMatches } = matchQuery
  const archive = useArchive()
  const predict = usePredict()
  const loadPrediction = predict.mutate
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
  const predictionInput = useMemo(() => {
    if (!match?.raw_match) return undefined
    return {
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
  }, [match])

  useEffect(() => {
    if (predictionInput) loadPrediction(predictionInput)
  }, [predictionInput, loadPrediction])

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
        <button type="button" onClick={backToGames} className="mb-4 min-h-11 text-sm font-semibold text-blue-a hover:underline">← Zurück zur Übersicht</button>
        <QueryState title="Spiel nicht gefunden" message="Dieses Spiel ist in der aktuellen Spielliste nicht enthalten. Kehre zur Übersicht zurück und wähle ein anderes Spiel." />
      </PageTransition>
    )
  }

  const kickoff = match.raw_match?.commence_time
  const hasKickoff = Boolean(kickoff && Number.isFinite(Date.parse(kickoff)))
  const kickoffLabel = hasKickoff ? `${shortDate(kickoff)} · ${kickoffTime(kickoff)}` : 'Anstoßzeit nicht verfügbar'
  const cachedModelTip = match.model_tip ?? match.top_tip
  const modelTip = predict.data?.model_tip ?? predict.data?.top_tip ?? cachedModelTip
  const activeTip = modelTip && modelTip !== 'N/A' ? modelTip : null
  const fixtureState = fixtureStatus(match, now)
  const isUpcoming = fixtureState === 'upcoming'
  const canCopy = isUpcoming && Boolean(activeTip)
  const probabilities = predict.data?.probabilities ?? match.probabilities
  const hasBookmakerOdds = Boolean(match.odds && [match.odds.home, match.odds.draw, match.odds.away].every((price) => Number.isFinite(price) && price > 1))
  const probs = hasBookmakerOdds
    ? computeImpliedProbs(match.odds)
    : (probabilities ?? { home: 0, draw: 0, away: 0 })
  const hasOutcomeProbabilities = probs.home + probs.draw + probs.away > 0
  const quoteSource = hasBookmakerOdds ? 'Buchmacherquoten' : (probabilities ? 'Elo-Modell, keine Wettquote' : 'Keine Quoten oder Modellwerte')
  const quoteObservedAt = hasBookmakerOdds ? match.odds_observed_at : (predict.data?.observed_at ?? match.observed_at)
  const observedAt = predict.data?.observed_at ?? match.observed_at
  const dataStatus = predict.data?.source_status ?? predict.data?.status ?? match.source_status ?? match.status
  const dataStatusLabel = formatDataStatus(dataStatus, observedAt, now)
  const dataSource = predict.data?.source ?? match.source
  const tipInsights = rankedTipInsights(predict.data?.xp_tips, predict.data?.matrix)
  const xgHome = predict.data?.xg_home ?? match.xg_home
  const xgAway = predict.data?.xg_away ?? match.xg_away
  const xgTotal = (xgHome ?? 0) + (xgAway ?? 0)
  const missing = Object.entries(match.lineup_diff ?? {}).filter(([, value]) => value.missing?.length)
  const stage = stageLabel(match.stage)

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
      <button type="button" onClick={backToGames} className="mb-4 min-h-11 text-sm font-semibold text-blue-a hover:underline">← Zurück zur Übersicht</button>
      {matchesError && <div className="mb-4"><QueryState title="Spiele konnten nicht aktualisiert werden" message="Die zuletzt geladenen Spielinformationen werden angezeigt. Prüfe die Verbindung und lade die Liste erneut." onRetry={() => { void retryMatches() }} /></div>}

      <header className="match-heading">
        <div className="flex flex-wrap items-center gap-2 text-sm text-fg-2">
          <span>{stage}{match.is_ko_phase ? ' · K.-o.-Phase' : ''}</span>
          <span aria-hidden="true">·</span>
          <span>{kickoffLabel}</span>
          <span className="rounded-full bg-surface-2 px-2.5 py-1 text-xs font-medium">{matchStatusLabel(match, now)}</span>
        </div>
        <h1 className="mt-5 grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 text-xl font-semibold tracking-tight text-fg sm:gap-5 sm:text-3xl">
          <span className="flex min-w-0 items-center gap-2"><TeamLogo name={match.home_team} src={match.home_logo} className="h-6 w-6 sm:h-8 sm:w-8" /><span className="min-w-0 break-words">{match.home_team}</span></span>
          <span className="text-xs font-medium text-fg-3 sm:text-sm">gegen</span>
          <span className="flex min-w-0 items-center justify-end gap-2 text-right"><span className="min-w-0 break-words">{match.away_team}</span><TeamLogo name={match.away_team} src={match.away_logo} className="h-6 w-6 sm:h-8 sm:w-8" /></span>
        </h1>
        <button type="button" onClick={() => { setSelectedTeams([match.home_team, match.away_team]); navigate('/team-form') }} className="mt-4 min-h-11 rounded-lg border border-line-2 px-4 text-sm font-semibold text-fg hover:bg-surface-2">
          Diese Teams vergleichen
        </button>
      </header>

      <section aria-labelledby="recommendation-title" className="mb-5 rounded-xl border border-line bg-surface p-5 sm:p-6">
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.8fr)]">
          <div className="recommendation-main">
            <p className="text-sm font-medium text-fg-2">Modellvorschlag nach erwarteten Tippspielpunkten</p>
            <h2 id="recommendation-title" className="mt-1 text-base font-semibold text-fg">Empfohlener Ergebnistipp</h2>
            <p className="mt-3 text-5xl font-bold tracking-tight tabular-nums text-fg sm:text-6xl">{activeTip ?? '–'}</p>
            <div className="mt-4 space-y-1 text-sm text-fg-2" aria-live="polite">
              <p><span className="font-medium text-fg">Quelle:</span> {sourceLabel(dataSource)}</p>
              <p><span className="font-medium text-fg">Datenstand:</span> {formatObservedAt(observedAt)}</p>
              <p><span className="font-medium text-fg">Datenstatus:</span> {dataStatusLabel}</p>
              {dataStatusLabel === 'Älterer Datenstand' && <p className="text-amber-a">Die Daten sind älter als 24 Stunden. Quoten und Teaminformationen können sich inzwischen geändert haben.</p>}
            </div>
            {predict.isPending && <p role="status" className="mt-3 text-xs text-fg-3">Die Spielanalyse wird aktualisiert. Der vorhandene Spieltipp bleibt sichtbar.</p>}
            {predict.isError && <div className="mt-3 rounded-lg border border-line bg-surface-2 p-3 text-sm text-fg-2" role="alert">
              <p>Die Aktualisierung der Spielanalyse ist fehlgeschlagen{activeTip ? '; der vorhandene Spieltipp wird weiterhin angezeigt.' : '.'}</p>
              {predictionInput && <button type="button" onClick={() => predict.mutate(predictionInput)} className="mt-2 min-h-11 font-semibold text-blue-a underline">Analyse erneut laden</button>}
            </div>}
            {predict.isSuccess && !predict.data?.model_tip && !predict.data?.top_tip && !activeTip && <p className="mt-3 text-sm text-fg-2">Für dieses Spiel ist keine Ergebnismitteilung verfügbar.</p>}
          </div>

          <div className="space-y-4">
            <div className="rounded-lg border border-line bg-surface-2 p-4">
              <p className="text-sm font-semibold text-fg">Modelltipp kopieren</p>
              <p className="mt-1 text-xs leading-relaxed text-fg-2">Kopiert nur den Vorschlag in deine Zwischenablage und speichert ihn nicht.</p>
              <button type="button" onClick={() => { void copyTip() }} disabled={!canCopy} className="mt-3 min-h-11 rounded-lg bg-action px-4 text-sm font-semibold text-on-action hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50">Tipp kopieren</button>
              {copyStatus && <p role="status" className="mt-2 text-xs text-fg-2">{copyStatus}</p>}
            </div>

            <SharedTipEditor key={`${competition}:${match.id}`} match={match} competition={competition} savedTip={archive.data?.[match.id]?.prediction.user_tip} now={now} />
          </div>
        </div>

        <aside className="mt-5 rounded-lg border border-line bg-surface-2 px-4 py-3 text-sm leading-relaxed text-fg-2">
          <strong className="text-fg">Gemeinsamer Spieltipp:</strong> Ein gespeicherter Tipp wird zentral für dieses Spiel abgelegt. Er ist nicht nutzergetrennt, keinem persönlichen Konto zugeordnet und kann für alle sichtbar sein.
        </aside>
      </section>

      {missing.length > 0 && (
        <section className="mb-5 rounded-xl border border-line bg-surface p-4" aria-labelledby="lineup-title">
          <h2 id="lineup-title" className="text-base font-semibold text-fg">Fehlende Spieler in der Aufstellung</h2>
          {missing.map(([team, value]) => <p key={team} className="mt-2 text-sm text-fg-2"><b className="text-fg">{team}:</b> {value.missing.join(', ')}</p>)}
        </section>
      )}

      <section className="mb-5 rounded-xl border border-line bg-surface" aria-labelledby="analysis-title">
        <div className="border-b border-line px-5 py-4">
          <h2 id="analysis-title" className="text-base font-semibold text-fg">Spielanalyse</h2>
          <p className="mt-1 text-sm text-fg-2">Siegchance und mögliche Ergebnistipps</p>
        </div>
        <div className="grid lg:grid-cols-2">
          <div className="p-5 lg:border-r lg:border-line">
            <h3 className="text-sm font-semibold text-fg">Wer gewinnt?</h3>
            <p className="mt-1 text-sm text-fg-2">Die Chancen beziehen sich auf Sieg oder Remis, nicht auf ein genaues Ergebnis.</p>
            {hasOutcomeProbabilities ? (
              <>
                <div className="mt-5 flex h-4 overflow-hidden rounded-full bg-surface-2" role="img" aria-label={`${match.home_team} Sieg ${pct(probs.home)}, Unentschieden ${pct(probs.draw)}, ${match.away_team} Sieg ${pct(probs.away)}`}>
                  <span className="bg-blue-a" style={{ width: `${probs.home * 100}%` }} />
                  <span className="bg-fg-3" style={{ width: `${probs.draw * 100}%` }} />
                  <span className="bg-line-2" style={{ width: `${probs.away * 100}%` }} />
                </div>
                <div className="mt-4 grid grid-cols-3 gap-2 text-xs text-fg-2">
                  <div><span className="mb-1 block h-1.5 w-5 rounded-full bg-blue-a" /><b className="block text-base tabular-nums text-fg">{pct(probs.home)}</b>{match.home_team}</div>
                  <div><span className="mb-1 block h-1.5 w-5 rounded-full bg-fg-3" /><b className="block text-base tabular-nums text-fg">{pct(probs.draw)}</b>Unentschieden</div>
                  <div><span className="mb-1 block h-1.5 w-5 rounded-full bg-line-2" /><b className="block text-base tabular-nums text-fg">{pct(probs.away)}</b>{match.away_team}</div>
                </div>
                <p className="mt-4 text-xs text-fg-3">Quelle: {quoteSource} · {quoteObservedAt ? formatObservedAt(quoteObservedAt) : 'Zeitpunkt nicht verfügbar'}</p>
              </>
            ) : <p className="mt-4 text-sm text-fg-2">Für diese Einschätzung sind keine Daten verfügbar.</p>}
          </div>

          <div className="border-t border-line p-5 lg:border-t-0">
            <h3 className="text-sm font-semibold text-fg">Welche Ergebnisse kommen infrage?</h3>
            <p className="mt-1 text-sm text-fg-2">Die besten Optionen nach durchschnittlich erwarteten Tippspielpunkten.</p>
            {tipInsights.length ? (
              <div className="mt-3 divide-y divide-line">
                {tipInsights.map((item, index) => (
                  <div key={item.tip} className="flex items-center justify-between gap-4 py-3">
                    <div className="flex items-center gap-3"><span className="text-xl font-semibold tabular-nums text-fg">{item.tip}</span>{index === 0 && <span className="rounded-full bg-blue-a/10 px-2 py-1 text-xs font-medium text-blue-a">Empfehlung</span>}</div>
                    <div className="text-right"><div className="text-sm font-semibold tabular-nums text-fg">{item.expectedPoints.toFixed(2)} Punkte</div><div className="text-xs tabular-nums text-fg-3">{item.exactChance === null ? 'Trefferchance nicht verfügbar' : `${(item.exactChance * 100).toFixed(1)} % genau`}</div></div>
                  </div>
                ))}
                <p className="pt-3 text-xs leading-relaxed text-fg-3">Erwartete Punkte sind der Durchschnitt über mögliche Ergebnisse. Die Chance für den exakten Treffer ist eine separate Angabe.</p>
              </div>
            ) : (
              <p className="mt-4 text-sm text-fg-2">{predict.isError ? 'Die Ergebnistipps konnten nicht berechnet werden.' : predict.isPending ? 'Die Ergebnistipps werden berechnet.' : 'Für dieses Spiel liegen keine weiteren Ergebnistipps vor.'}</p>
            )}
          </div>
        </div>
      </section>

      <section className="mb-5 rounded-xl border border-line bg-surface p-5" aria-labelledby="context-title">
        <h2 id="context-title" className="text-base font-semibold text-fg">Spielausgang und zusätzliche Hinweise</h2>
        <div className="mt-3"><MatchHintCard match={match} /></div>
        {xgHome != null && xgAway != null && xgTotal > 0 && (
          <div className="mt-5 border-t border-line pt-4">
            <h3 className="text-sm font-semibold text-fg">Erwartete Tore</h3>
            <div className="mt-3 grid gap-4 sm:grid-cols-2">
              {[
                { team: match.home_team, xg: xgHome, form: match.home_form },
                { team: match.away_team, xg: xgAway, form: match.away_form },
              ].map(({ team, xg, form }) => (
                <div key={team}>
                  <div className="flex items-center justify-between gap-2 text-sm font-medium text-fg"><span>{team}</span><span className="tabular-nums">{xg.toFixed(2)}</span></div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-2"><div className="h-full rounded-full bg-blue-a" style={{ width: `${(xg / xgTotal) * 100}%` }} /></div>
                  <p className="mt-2 text-xs text-fg-2">{recentFormSummary(form)}{form?.status === 'stale' ? ' · Datenstand möglicherweise veraltet' : ''}</p>
                </div>
              ))}
            </div>
            <p className="mt-2 text-xs text-fg-3">Die Werte beschreiben einen Modelldurchschnitt und sind kein garantiertes Ergebnis.</p>
          </div>
        )}
      </section>

      <details className="mb-5 overflow-hidden rounded-xl border border-line bg-surface">
        <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between px-5 py-4 text-base font-semibold text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-a [&::-webkit-details-marker]:hidden">
          Weitere Daten zur Analyse <span aria-hidden="true">⌄</span>
        </summary>
        <div className="space-y-4 border-t border-line p-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <section className="rounded-xl border border-line p-4">
              <h3 className="text-base font-semibold text-fg">Letzte Pflichtspiele</h3>
              <p className="mt-1 text-xs text-fg-3">Formdaten umfassen Wettbewerbe ausserhalb dieser Liga.</p>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div><div className="flex items-center gap-2 text-sm font-medium text-fg"><TeamLogo name={match.home_team} />{match.home_team}</div><div className="mt-2"><FormBadges form={match.home_form} /></div><TeamFormHistory team={match.home_team} form={match.home_form} kickoff={kickoff} /></div>
                <div><div className="flex items-center gap-2 text-sm font-medium text-fg"><TeamLogo name={match.away_team} />{match.away_team}</div><div className="mt-2"><FormBadges form={match.away_form} /></div><TeamFormHistory team={match.away_team} form={match.away_form} kickoff={kickoff} /></div>
              </div>
            </section>

            <section className="rounded-xl border border-line p-4">
              <h3 className="text-base font-semibold text-fg">Sieg, Remis, Niederlage</h3>
              <p className="mt-1 text-xs text-fg-2">{quoteSource}{quoteObservedAt ? ` · ${formatObservedAt(quoteObservedAt)}` : ''}</p>
              {hasOutcomeProbabilities ? (
                <div className="mt-4 space-y-3">
                  {[
                    { label: `${match.home_team} gewinnt`, price: hasBookmakerOdds ? match.odds?.home : (probs.home > 0 ? 1 / probs.home : undefined), probability: probs.home, color: 'var(--blue)' },
                    { label: 'Unentschieden', price: hasBookmakerOdds ? match.odds?.draw : (probs.draw > 0 ? 1 / probs.draw : undefined), probability: probs.draw, color: 'var(--text-3)' },
                    { label: `${match.away_team} gewinnt`, price: hasBookmakerOdds ? match.odds?.away : (probs.away > 0 ? 1 / probs.away : undefined), probability: probs.away, color: 'var(--border-2)' },
                  ].map(({ label, price, probability, color }) => (
                    <div key={label}>
                      <div className="flex items-baseline justify-between gap-3 text-sm"><span className="font-medium text-fg">{label}</span><span className="tabular-nums text-fg-2">{pct(probability)}{price ? ` · Quote ${price.toFixed(2)}` : ''}</span></div>
                      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-2"><div className="h-full" style={{ width: `${probability * 100}%`, background: color }} /></div>
                    </div>
                  ))}
                </div>
              ) : <p className="mt-3 text-sm text-fg-2">Keine Werte verfügbar.</p>}
            </section>

            <section className="rounded-xl border border-line p-4">
              <h3 className="text-base font-semibold text-fg">Wahrscheinlichkeit je Ergebnis</h3>
              <div className="mt-4">
                {predict.data?.matrix ? <ScoreHeatmap calc={predict.data} homeDisp={match.home_disp || match.home_team} awayDisp={match.away_disp || match.away_team} /> : <p className="text-sm text-fg-2">Für die Ergebnistabelle sind keine Daten verfügbar.</p>}
              </div>
            </section>

            <section className="rounded-xl border border-line p-4">
              <h3 className="text-base font-semibold text-fg">Weitere Modelltipps</h3>
              {predict.data?.xp_tips?.length ? (
                <ol className="mt-3 divide-y divide-line">
                  {predict.data.xp_tips.slice(0, 5).map((item, index) => <li key={item.Tipp} className="flex items-center justify-between gap-3 py-2 text-sm"><span className="text-fg-2">{index + 1}. <b className="ml-1 tabular-nums text-fg">{item.Tipp}</b></span><span className="tabular-nums text-fg-2">{item.xP.toFixed(2)} erwartete Punkte</span></li>)}
                </ol>
              ) : <p className="mt-3 text-sm text-fg-2">Keine weiteren Modelltipps verfügbar.</p>}
            </section>

            {match.bots && Object.keys(match.bots).length > 0 && (
              <section className="rounded-xl border border-line p-4">
                <h3 className="text-base font-semibold text-fg">Bot-Vorschläge</h3>
                <ul className="mt-3 grid grid-cols-2 gap-2">
                  {(Object.keys(BOT_LABELS) as BotKey[]).map((key) => {
                    const tip = match.bots?.[key]?.tip
                    return tip ? <li key={key} className="flex items-center justify-between gap-2 rounded-lg bg-surface-2 px-3 py-2 text-sm"><span className="text-fg-2">{BOT_LABELS[key]}</span><b className="tabular-nums text-fg">{tip}</b></li> : null
                  })}
                </ul>
              </section>
            )}

            <PoolContextEditor
              pool={pool}
              form={poolForm}
              onFormChange={setPoolForm}
              open={poolOpen}
              onToggle={() => setPoolOpen((current) => !current)}
              status={poolStatus}
              onSave={savePoolContext}
              saving={savePool.isPending}
            />
          </div>
        </div>
      </details>
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
