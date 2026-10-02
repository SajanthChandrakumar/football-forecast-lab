import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useAppState } from '../../state/AppState'
import { useMatches, useMatchHistory, usePredict, useSaveUserTip } from '../../hooks/queries'
import { computeImpliedProbs, pct, cn } from '../../lib/util'
import { shortDate } from '../../lib/format'
import { fixtureStatus, sharedTipIsOpen } from '../../lib/fixture-status.mjs'
import type { BotKey, Match, TeamForm, TeamFormMatch } from '../../lib/types'
import { GlassCard, SectionTitle } from '../../components/shared/GlassCard'
import { FormBadges, TeamLogo } from '../../components/shared/Badges'
import { MatchHintCard } from '../../components/shared/MatchHintCard'
import { PageTransition } from '../../components/shared/PageTransition'
import { ChartSkeleton, CardGridSkeleton } from '../../components/shared/Skeleton'
import { ScoreHeatmap } from './ScoreHeatmap'
import { OddsHistory } from './OddsHistory'
import { matchFormInsights, rankedTipInsights, matchLoadSummary, playerFormStatusMessage, playerFormSummary, teamHistoryAnalysis, teamHistoryMetrics } from '../../lib/tip-insights.mjs'
import { lineupState } from '../../lib/match-intelligence.mjs'
import { lineupRows } from '../../lib/lineup-layout.mjs'
import type { MatchLineup, MatchPlayer } from '../../lib/types'

const BOT_META: Record<BotKey, { label: string; color: string }> = {
  broker: { label: 'Broker', color: 'var(--blue)' },
  professor: { label: 'Professor', color: 'var(--emerald)' },
  sniper: { label: 'X-Sniper', color: 'var(--purple)' },
  gambler: { label: 'Zocker', color: 'var(--text-2)' },
}

function TeamFormHistory({ team, form, kickoff }: { team: string; form?: TeamForm; kickoff?: string }) {
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
          {items.map((item) => <HistoricalMatchRow key={item.fixture_id} item={item} />)}
        </ul>
      ) : (
        <p className="mt-3 text-sm font-semibold text-fg-2">Form nicht verfügbar</p>
      )}
    </section>
  )
}

function HistoricalMatchRow({ item }: { item: TeamFormMatch }) {
  const [open, setOpen] = useState(false)
  const history = useMatchHistory(item.fixture_id, open)
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
      <button type="button" onClick={() => setOpen((value) => !value)} className="mt-2 min-h-9 text-xs font-bold text-emerald-a underline underline-offset-4">
        {open ? 'Aufstellung schließen' : 'Aufstellung ansehen'}
      </button>
      {open && (
        <div className="mt-3 border-t border-line pt-3">
          {history.isLoading ? <p className="text-xs text-fg-2">Aufstellung wird geladen…</p> : hasCompleteLineups ? (
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
  const { competition } = useAppState()
  const isPremierLeague = competition === 'epl2026'
  const navigate = useNavigate()
  const { data: matches } = useMatches()
  const predict = usePredict()
  const saveTip = useSaveUserTip()
  const [adoptStatus, setAdoptStatus] = useState('')
  const [copyStatus, setCopyStatus] = useState('')
  const [showOddsHistory, setShowOddsHistory] = useState(false)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const clock = window.setInterval(() => setNow(Date.now()), 15_000)
    return () => window.clearInterval(clock)
  }, [])

  const match: Match | undefined = useMemo(
    () => matches?.find((m) => m.id === id),
    [matches, id],
  )

  // Recalculate from backend-provided match context; there is no client KO toggle.
  useEffect(() => {
    if (match?.raw_match) {
      predict.mutate({
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
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [match?.id])
  if (!matches) {
    return (
      <PageTransition>
        <div className="space-y-4">
          <ChartSkeleton />
          <CardGridSkeleton count={2} />
        </div>
      </PageTransition>
    )
  }
  if (!match) return <p className="text-red-a">Match nicht gefunden.</p>

  const calc = predict.data
  const hasBookmakerOdds = Boolean(match.odds && [match.odds.home, match.odds.draw, match.odds.away]
    .every((price) => Number.isFinite(price) && price > 1))
  const modelProbabilities = calc?.probabilities ?? match.probabilities
  const hasModelOdds = !hasBookmakerOdds && Boolean(modelProbabilities)
  const probs = hasBookmakerOdds
    ? computeImpliedProbs(match.odds)
    : (modelProbabilities ?? { home: 0, draw: 0, away: 0 })
  const quoteSource = hasBookmakerOdds
    ? 'Buchmacherquote'
    : (hasModelOdds ? 'Elo-Modellquote – nicht wettbar' : 'Nicht verfügbar')
  const quoteObservedAt = hasBookmakerOdds ? match.odds_observed_at : (calc?.observed_at ?? match.observed_at)
  const modelTip = calc?.model_tip ?? match.model_tip ?? calc?.top_tip
  const topTip = calc?.xp_tips?.find((tip) => tip.Tipp === modelTip) ?? calc?.xp_tips?.[0]
  const activeTip = topTip?.Tipp ?? modelTip ?? match.top_tip
  const canTip = fixtureStatus(match, now) === 'upcoming' && Boolean(activeTip) && activeTip !== 'N/A'
  const canSaveSharedTip = canTip && sharedTipIsOpen(match.raw_match?.commence_time, now)
  const runners = calc?.xp_tips?.slice(1, 4) ?? []
  const tipInsights = rankedTipInsights(calc?.xp_tips, calc?.matrix)
  const formInsights = fixtureStatus(match, now) === 'upcoming'
    ? matchFormInsights(match.home_team, match.home_form, match.away_team, match.away_form)
    : []
  const hasOutcomeProbabilities = probs.home + probs.draw + probs.away > 0
  const missing = Object.entries(match.lineup_diff ?? {}).filter(([, v]) => v.missing?.length)
  const lineup = lineupState(match.match_intelligence, match.home_team, match.away_team)

  const adopt = () => {
    if (!activeTip || !sharedTipIsOpen(match.raw_match?.commence_time)) {
      setNow(Date.now())
      setAdoptStatus('Gemeinsamer Tipp ist geschlossen (5 Minuten vor Anstoß).')
      return
    }
    setAdoptStatus('Speichere…')
    saveTip.mutate(
      { matchId: match.id, tip: activeTip },
      {
        onSuccess: () => setAdoptStatus('✓ Gemeinsamer Spieltipp gespeichert'),
        onError: (e) => setAdoptStatus(`Fehler: ${(e as Error).message}`),
      },
    )
  }

  const copyTip = async () => {
    if (!activeTip || fixtureStatus(match) !== 'upcoming') {
      setNow(Date.now())
      return
    }
    try {
      await navigator.clipboard.writeText(activeTip)
      setCopyStatus('Tipp kopiert. Du kannst ihn jetzt in deine Tipprunde einfügen.')
    } catch {
      setCopyStatus('Kopieren nicht möglich. Bitte den Tipp manuell markieren.')
    }
  }

  return (
    <PageTransition>
      <button onClick={() => navigate(-1)} className="mb-4 text-sm font-semibold text-fg-2 hover:text-fg">
        ← Zurück
      </button>

      <header className="relative mb-5 overflow-hidden rounded-[1.75rem] bg-[#193b2b] px-5 py-6 text-[#f8f7f2] shadow-[0_18px_35px_-25px_rgba(22,48,33,0.8)] sm:px-8 sm:py-8">
        <div className="absolute inset-x-0 top-0 h-1 bg-[#c9ad78]" aria-hidden="true" />
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#cbdccf]">{isPremierLeague ? 'Premier League' : match.is_ko_phase ? 'K.-o.-Phase · doppelte Punkte' : match.stage === 'League stage' ? 'Ligaphase' : (match.stage ?? 'Ligaphase')}</p>
        <h1 className="mt-6 grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3 font-display text-3xl font-bold leading-none text-[#f8f7f2] sm:gap-6 sm:text-5xl">
          <span className="flex min-w-0 flex-col items-start gap-2 sm:flex-row sm:items-center"><TeamLogo name={match.home_team} src={match.home_logo} className="h-7 w-7" /><span className="min-w-0 break-words">{match.home_team}</span></span>
          <span className="font-sans text-sm font-medium text-[#b7cabd]">vs</span>
          <span className="flex min-w-0 flex-col items-end gap-2 text-right sm:flex-row-reverse sm:items-center"><TeamLogo name={match.away_team} src={match.away_logo} className="h-7 w-7" /><span className="min-w-0 break-words">{match.away_team}</span></span>
        </h1>
        <div className="mt-7 flex flex-col gap-5 border-t border-white/20 pt-6 min-[480px]:flex-row min-[480px]:items-end min-[480px]:justify-between">
          <div>
            <p className="text-sm text-[#cbdccf]">Unser Tipp</p>
            <div className="font-display text-6xl font-bold leading-none tabular-nums text-[#f8f7f2]">{activeTip && activeTip !== 'N/A' ? activeTip : '–'}</div>
            <p className="mt-1 text-xs text-[#cbdccf]">Nach erwarteten Tippspielpunkten</p>
          </div>
          {canTip ? (
            <div className="flex flex-col items-start gap-2 min-[480px]:items-end">
              <button type="button" onClick={copyTip} className="min-h-11 rounded-lg bg-[#f8f7f2] px-5 py-2.5 text-sm font-bold text-[#193b2b] transition hover:bg-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white">Tipp kopieren <span aria-hidden="true">↗</span></button>
              <button onClick={adopt} disabled={saveTip.isPending || !canSaveSharedTip} className="min-h-10 text-left text-sm font-medium text-[#e2ede4] underline underline-offset-4 hover:text-white disabled:opacity-50">{saveTip.isPending ? 'Speichere…' : canSaveSharedTip ? 'Gemeinsamen Spieltipp speichern' : 'Gemeinsamer Tipp geschlossen'}</button>
            </div>
          ) : (
            <p className="text-sm text-[#e2ede4]">{fixtureStatus(match, now) === 'pending' ? 'Ergebnis ausstehend · Tipps geschlossen.' : fixtureStatus(match, now) === 'played' ? 'Spiel abgeschlossen · Tipps geschlossen.' : 'Anstoßzeit fehlt · Tipp-Aktion geschlossen.'}</p>
          )}
        </div>
        <details className="mt-4 text-xs text-[#cbdccf]"><summary className="cursor-pointer underline-offset-4 hover:underline">Was passiert mit meinem Tipp?</summary><p className="mt-2 max-w-prose leading-relaxed">„Tipp kopieren“ überträgt ihn nicht an den Server. „Gemeinsamen Spieltipp speichern“ schreibt einen zentralen Eintrag für dieses Spiel; er ist derzeit nicht nutzergetrennt.</p></details>
        {copyStatus && <p role="status" className="mt-2 text-sm text-[#f8f7f2]">{copyStatus}</p>}
        {adoptStatus && <p role="status" className="mt-2 text-sm text-[#f8f7f2]">{adoptStatus}</p>}
      </header>

      <section className="mb-5 rounded-[1.5rem] bg-[var(--match-note-bg)] p-5 sm:p-7">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-a">Auf einen Blick</p>
        <h2 className="mt-1 font-display text-2xl font-bold text-fg">Was die Daten zeigen</h2>
        <div className="mt-4"><MatchHintCard match={match} /></div>
        {formInsights.length > 0 && (
          <div className="mt-5 border-t border-line pt-4">
            <p className="text-sm font-bold text-fg">Aus den letzten Spielen</p>
            <ul className="mt-3 grid gap-3">
              {formInsights.map((insight) => (
                <li key={insight.kind} className={cn(
                  'relative overflow-hidden rounded-2xl border px-5 py-4',
                  insight.kind === 'form'
                    ? 'border-[#c5d4c6] bg-[#fffdfa] shadow-[0_12px_28px_-22px_rgba(22,48,33,0.55)] before:absolute before:inset-y-0 before:left-0 before:w-1.5 before:bg-[#b69b68]'
                    : 'border-line bg-surface/70',
                )}>
                  <p className="text-xs font-bold uppercase tracking-[0.14em] text-emerald-a">{insight.kind === 'form' ? 'Formvergleich' : 'Tore'}</p>
                  <p className={cn('mt-1 font-display font-bold leading-tight text-fg', insight.kind === 'form' ? 'text-2xl' : 'text-xl')}>{insight.title}</p>
                  <p className="mt-2 text-base leading-relaxed text-fg-2">{insight.detail}</p>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-fg-3">Der Ergebnistipp ist auf Tippspielpunkte berechnet. {match.home_form?.scope === 'league' || match.away_form?.scope === 'league' ? 'Die Form beschreibt separat zuletzt erfasste Premier-League-Spiele, keine anderen Wettbewerbe.' : 'Die Form beschreibt separat die letzten erfassten Pflichtspiele aller Wettbewerbe.'}{match.home_form?.status === 'stale' || match.away_form?.status === 'stale' ? ' Datenstand möglicherweise veraltet.' : ''}</p>
          </div>
        )}
      </section>

      {missing.length > 0 && (
        <GlassCard className="mb-5 border-amber-a/40 bg-amber-a/5">
          <SectionTitle className="mb-2 text-amber-a">Aufstellungs-Alarm</SectionTitle>
          {missing.map(([team, v]) => <p key={team} className="text-sm text-fg-2"><b className="text-fg">{team}:</b> fehlend — {v.missing.join(', ')}</p>)}
        </GlassCard>
      )}

      <GlassCard className="mb-5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-a">Kurz vor Anpfiff</p>
            <SectionTitle className="mt-1">Aufstellungen & Spieler</SectionTitle>
          </div>
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
        {match.match_intelligence?.injuries?.status === 'unavailable' && (
          <p className="mt-4 text-xs text-fg-3">Verletzungsdaten derzeit nicht zuverlässig verfügbar.</p>
        )}
      </GlassCard>

      <section className="mb-5 overflow-hidden rounded-[1.5rem] border border-line bg-surface shadow-[0_18px_35px_-32px_rgba(22,48,33,0.55)]">
        <div className="border-b border-line px-5 py-5 sm:px-7">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-a">Tipp-Check</p>
          <h2 className="mt-1 font-display text-3xl font-bold text-fg">So liest du dieses Spiel</h2>
        </div>
        <div className="grid lg:grid-cols-2">
        <div className="px-5 py-6 sm:px-7 lg:border-r lg:border-line">
          <h3 className="text-lg font-bold text-fg">Wer gewinnt?</h3>
          <p className="mt-1 text-sm leading-relaxed text-fg-2">Siegchance, unabhängig vom genauen Ergebnis.</p>
          {hasOutcomeProbabilities ? (
            <div className="mt-6">
              <div className="flex h-5 overflow-hidden rounded-full bg-surface-2" role="img" aria-label={`${match.home_team} Sieg ${pct(probs.home)}, Unentschieden ${pct(probs.draw)}, ${match.away_team} Sieg ${pct(probs.away)}`}>
                <span className="bg-[#2c6049]" style={{ width: `${probs.home * 100}%` }} />
                <span className="bg-[#9aa99c]" style={{ width: `${probs.draw * 100}%` }} />
                <span className="bg-[#bf795b]" style={{ width: `${probs.away * 100}%` }} />
              </div>
              <div className="mt-4 grid grid-cols-3 gap-2 text-xs text-fg-2">
                <div><span className="mb-1 block h-1.5 w-5 rounded-full bg-[#2c6049]" /><b className="block text-base tabular-nums text-fg">{pct(probs.home)}</b>{match.home_team}</div>
                <div><span className="mb-1 block h-1.5 w-5 rounded-full bg-[#9aa99c]" /><b className="block text-base tabular-nums text-fg">{pct(probs.draw)}</b>Remis</div>
                <div><span className="mb-1 block h-1.5 w-5 rounded-full bg-[#bf795b]" /><b className="block text-base tabular-nums text-fg">{pct(probs.away)}</b>{match.away_team}</div>
              </div>
              <p className="mt-5 text-xs text-fg-3">Quelle: {quoteSource}. {hasBookmakerOdds ? 'Buchmacherquoten ohne Marge.' : 'Modellschätzung; keine wettbare Quote.'}</p>
            </div>
          ) : <p className="mt-4 text-sm text-fg-2">Für diese Einschätzung fehlen Daten.</p>}
        </div>

        <div className="border-t border-line px-5 py-6 sm:px-7 lg:border-t-0">
          <h3 className="text-lg font-bold text-fg">Welches Ergebnis tippen?</h3>
          <p className="mt-1 text-sm leading-relaxed text-fg-2">Die drei besten Optionen nach erwarteten Punkten.</p>
          {tipInsights.length ? (
            <div className="mt-4 divide-y divide-line">
              {tipInsights.map((item, index) => (
                <div key={item.tip} className="flex items-center justify-between gap-4 py-3">
                  <div className="flex items-center gap-3"><span className={cn('font-display text-2xl font-bold tabular-nums', index === 0 ? 'text-emerald-a' : 'text-fg')}>{item.tip}</span>{index === 0 && <span className="text-xs font-semibold text-emerald-a">Empfehlung</span>}</div>
                  <div className="text-right"><div className="text-sm font-bold tabular-nums text-fg">{item.expectedPoints.toFixed(2)} xP</div><div className="text-xs tabular-nums text-fg-3">{item.exactChance === null ? 'Chance offen' : `${(item.exactChance * 100).toFixed(1)} % exakt`}</div></div>
                </div>
              ))}
              <p className="pt-3 text-xs leading-relaxed text-fg-3">xP = durchschnittliche Tippspielpunkte über alle möglichen Ergebnisse. Die exakte Trefferchance ist eine andere Zahl.</p>
            </div>
          ) : <p className="mt-4 text-sm text-fg-2">Die Tipp-Alternativen werden berechnet oder sind nicht verfügbar.</p>}
        </div>
        </div>
      </section>

      <details className="mb-4 rounded-2xl border border-line bg-surface px-5 py-4" onToggle={(event) => setShowOddsHistory(event.currentTarget.open)}>
        <summary className="min-h-6 cursor-pointer text-sm font-bold text-fg">Wie haben sich die Quoten verändert?</summary>
        <OddsHistory matchId={match.id} homeTeam={match.home_team} awayTeam={match.away_team} enabled={showOddsHistory} />
      </details>

      <details className="mb-4 overflow-hidden rounded-2xl border border-line bg-surface">
        <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between px-5 py-3 text-sm font-bold text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-a [&::-webkit-details-marker]:hidden">
          Ausführliche Daten und Score-Tabelle <span aria-hidden="true">⌄</span>
        </summary>
        <div className="space-y-4 border-t border-line p-4">
      <div className="grid gap-4 lg:grid-cols-2">
        {/* xG + Form */}
        <GlassCard>
          <SectionTitle className="mb-4">Expected Goals & Form</SectionTitle>
          <div className="grid grid-cols-2 gap-4">
            {[
              { team: match.home_team, logo: match.home_logo, xg: calc?.xg_home, form: match.home_form },
              { team: match.away_team, logo: match.away_logo, xg: calc?.xg_away, form: match.away_form },
            ].map(({ team, logo, xg, form }) => (
              <div key={team} className="text-center">
                <div className="inline-flex items-center justify-center gap-2 text-sm font-semibold text-fg-2"><TeamLogo name={team} src={logo} className="h-5 w-5" />{team}</div>
                <div className="display-num mt-1 text-4xl text-emerald-a">{xg?.toFixed(2) ?? '…'}</div>
                <div className="mt-2 flex justify-center"><FormBadges form={form} /></div>
              </div>
            ))}
          </div>
          <div className="mt-5 grid gap-3 lg:grid-cols-2">
            <TeamFormHistory team={match.home_team} form={match.home_form} kickoff={match.raw_match?.commence_time} />
            <TeamFormHistory team={match.away_team} form={match.away_form} kickoff={match.raw_match?.commence_time} />
          </div>
        </GlassCard>

        {/* Real bookmaker prices or explicitly non-bettable fair model prices. */}
        <GlassCard>
          <SectionTitle className="mb-1">1 / X / 2</SectionTitle>
          <p className="mb-4 text-[10px] text-fg-3">
            {quoteSource}{quoteObservedAt ? ` · Stand ${quoteObservedAt}` : ''}
          </p>
          <div className="space-y-3">
            {[
              { label: `${match.home_team} Sieg`, price: hasBookmakerOdds ? match.odds?.home : (probs.home > 0 ? 1 / probs.home : undefined), p: probs.home, color: 'var(--blue)' },
              { label: 'Unentschieden', price: hasBookmakerOdds ? match.odds?.draw : (probs.draw > 0 ? 1 / probs.draw : undefined), p: probs.draw, color: 'var(--text-3)' },
              { label: `${match.away_team} Sieg`, price: hasBookmakerOdds ? match.odds?.away : (probs.away > 0 ? 1 / probs.away : undefined), p: probs.away, color: 'var(--red)' },
            ].map(({ label, price, p, color }) => (
              <div key={label}>
                <div className="flex items-baseline justify-between text-sm">
                  <span className="font-semibold text-fg">{label}</span>
                  <span className="tabular-nums text-fg-2">
                    {pct(p)} · <b className="text-fg">{price?.toFixed(2) ?? '–'}</b>
                  </span>
                </div>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-2">
                  <div className="h-full rounded-full transition-all" style={{ width: `${p * 100}%`, background: color }} />
                </div>
              </div>
            ))}
          </div>
        </GlassCard>

        {/* Heatmap */}
        <GlassCard>
          <SectionTitle className="mb-4">Score-Wahrscheinlichkeiten</SectionTitle>
          {calc?.matrix ? (
            <ScoreHeatmap calc={calc} modelTip={modelTip} homeDisp={match.home_disp || match.home_team} awayDisp={match.away_disp || match.away_team} />
          ) : (
            <p className="text-sm text-fg-3">{predict.isPending ? 'Rechne…' : 'Keine Daten'}</p>
          )}
        </GlassCard>

        {/* Tip ladder + bots */}
        <GlassCard>
          <SectionTitle className="mb-4">Tipp-Empfehlung</SectionTitle>
          <div className="mb-3">
            <TipSummary label="Model Tipp" tip={modelTip} status={calc?.status ?? match.status} />
          </div>
          <DataStatus
            status={calc?.source_status ?? match.source_status ?? match.status}
            source={calc?.source ?? match.source}
            observedAt={calc?.observed_at ?? match.observed_at}
            provenance={calc?.input_provenance ?? match.input_provenance}
          />
          {topTip ? (
            <>
              <div
                className="flex items-center justify-between rounded-xl border border-emerald-a/40 bg-emerald-dim px-4 py-3"
                style={{ boxShadow: '0 0 28px -8px color-mix(in srgb, var(--emerald) 50%, transparent), inset 0 1px 0 rgba(255,255,255,0.06)' }}
              >
                <div>
                <div className="text-[10px] font-bold uppercase tracking-widest text-emerald-a">Model Tipp</div>
                  <div className="display-num text-3xl text-fg">{topTip.Tipp}</div>
                </div>
                <div className="text-right">
                  <div className="text-[10px] font-bold uppercase tracking-widest text-fg-3">xP</div>
                  <div className="display-num text-2xl text-emerald-a">{topTip.xP.toFixed(2)}</div>
                </div>
              </div>
              <div className="mt-3 space-y-1.5">
                {runners.map((t, i) => (
                  <div key={t.Tipp} className="flex items-center justify-between rounded-lg bg-surface px-3 py-1.5 text-sm">
                    <span className="text-fg-2">#{i + 2} <b className="ml-1 text-fg tabular-nums">{t.Tipp}</b></span>
                    <span className="tabular-nums text-fg-3">{t.xP.toFixed(2)} xP</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="text-sm text-fg-3">{predict.isPending ? 'Rechne…' : 'Keine Empfehlung verfügbar'}</p>
          )}

          {match.bots && Object.keys(match.bots).length > 0 && (
            <div className="mt-5 border-t border-line pt-4">
              <SectionTitle className="mb-2">Bot Tips</SectionTitle>
              <div className="grid grid-cols-2 gap-2">
                {(Object.keys(BOT_META) as BotKey[]).map((key) => {
                  const tip = match.bots?.[key]?.tip
                  if (!tip) return null
                  return (
                    <div key={key} className="flex items-center justify-between rounded-lg bg-surface px-3 py-1.5 text-sm">
                      <span className="font-semibold" style={{ color: BOT_META[key].color }}>{BOT_META[key].label}</span>
                      <span className="display-num text-fg">{tip}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </GlassCard>
      </div>
        </div>
      </details>
    </PageTransition>
  )
}

function TipSummary({ label, tip, status }: { label: string; tip?: string | null; status?: string }) {
  const available = Boolean(tip) && status !== 'unavailable'
  return <div className="rounded-lg border border-line bg-surface px-3 py-2"><div className="text-[10px] font-bold uppercase tracking-wider text-fg-3">{label}</div><div className="display-num text-lg text-fg">{available ? tip : 'Unavailable'}</div><div className="text-[10px] text-fg-3">{status ?? 'unavailable'}</div></div>
}

function DataStatus({ status, source, observedAt, provenance }: { status?: string; source?: string | null; observedAt?: string | null; provenance?: Record<string, unknown> }) {
  const state = status ?? 'unavailable'
  return <div className="mb-3 rounded-lg border border-dashed border-line px-3 py-2 text-[10px] text-fg-3">Data: <b className="text-fg-2">{state}</b>{source ? ` · ${source}` : ''}{observedAt ? ` · ${observedAt}` : ''}{provenance && Object.keys(provenance).length > 0 ? ` · ${Object.keys(provenance).join(', ')}` : ' · provenance unavailable'}</div>
}
