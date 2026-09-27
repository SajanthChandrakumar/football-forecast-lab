import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMatches, usePoolContext, usePredict, useSavePoolContext, useSaveUserTip } from '../../hooks/queries'
import { computeImpliedProbs, pct, flag, cn } from '../../lib/util'
import { shortDate } from '../../lib/format'
import { fixtureStatus, sharedTipIsOpen } from '../../lib/fixture-status.mjs'
import type { BotKey, Match, TeamForm } from '../../lib/types'
import { GlassCard, SectionTitle } from '../../components/shared/GlassCard'
import { FormBadges, TeamLogo } from '../../components/shared/Badges'
import { MatchHintCard } from '../../components/shared/MatchHintCard'
import { PageTransition } from '../../components/shared/PageTransition'
import { ChartSkeleton, CardGridSkeleton } from '../../components/shared/Skeleton'
import { ScoreHeatmap } from './ScoreHeatmap'

const BOT_META: Record<BotKey, { label: string; color: string }> = {
  broker: { label: 'Broker', color: 'var(--blue)' },
  professor: { label: 'Professor', color: 'var(--emerald)' },
  sniper: { label: 'X-Sniper', color: 'var(--purple)' },
  gambler: { label: 'Zocker', color: 'var(--text-2)' },
}

function TeamFormHistory({ team, form }: { team: string; form?: TeamForm }) {
  if (!form?.status && !form?.matches?.length) return null
  const items = form?.matches?.slice(0, 5) ?? []
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
            Letzte Pflichtspiele · alle Wettbewerbe{sourceLabel ? ` · Quelle: ${sourceLabel}` : ''}
          </p>
        </div>
        {form?.status === 'stale' && <span className="text-xs font-semibold text-amber-a">Stand möglicherweise veraltet</span>}
      </div>
      {items.length ? (
        <ul className="mt-3 space-y-2">
          {items.map((item) => (
            <li key={item.fixture_id} className="rounded-lg bg-surface-2 px-3 py-2.5 text-sm">
              <div className="flex items-center justify-between gap-3">
                <span className="min-w-0 truncate font-semibold text-fg">{item.opponent_name}</span>
                <span className="shrink-0 font-bold tabular-nums text-fg">{item.score}</span>
              </div>
              <div className="mt-1 flex flex-wrap justify-between gap-x-2 text-xs text-fg-2">
                <span>{item.competition_name} · {item.venue === 'home' ? 'Heim' : 'Auswärts'}</span>
                <span>{shortDate(item.played_at)}</span>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm font-semibold text-fg-2">Form nicht verfügbar</p>
      )}
    </section>
  )
}

export function DetailView() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data: matches } = useMatches()
  const predict = usePredict()
  const saveTip = useSaveUserTip()
  const pool = usePoolContext(id)
  const savePool = useSavePoolContext()
  const [adoptStatus, setAdoptStatus] = useState('')
  const [copyStatus, setCopyStatus] = useState('')
  const [poolOpen, setPoolOpen] = useState(false)
  const [poolForm, setPoolForm] = useState({ user_points: '', leader_points: '', remaining_srf_max_points: '', tip_counts: '{}' })
  const [poolStatus, setPoolStatus] = useState('')
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
  useEffect(() => {
    if (!pool.data) return
    setPoolForm({
      user_points: String(pool.data.user_points),
      leader_points: String(pool.data.leader_points),
      remaining_srf_max_points: String(pool.data.remaining_srf_max_points),
      tip_counts: JSON.stringify(pool.data.tip_counts ?? {}, null, 0),
    })
  }, [pool.data])

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
  const poolTip = calc?.pool_tip ?? match.pool_tip
  const topTip = calc?.xp_tips?.find((tip) => tip.Tipp === modelTip) ?? calc?.xp_tips?.[0]
  const activeTip = topTip?.Tipp ?? modelTip ?? match.top_tip
  const canTip = fixtureStatus(match, now) === 'upcoming' && Boolean(activeTip) && activeTip !== 'N/A'
  const canSaveSharedTip = canTip && sharedTipIsOpen(match.raw_match?.commence_time, now)
  const runners = calc?.xp_tips?.slice(1, 4) ?? []
  const h2h = match.h2h
  const missing = Object.entries(match.lineup_diff ?? {}).filter(([, v]) => v.missing?.length)

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

  const savePoolContext = () => {
    let tipCounts: Record<string, number>
    try {
      tipCounts = JSON.parse(poolForm.tip_counts)
      if (!tipCounts || Array.isArray(tipCounts) || typeof tipCounts !== 'object') throw new Error('JSON object required')
    } catch {
      setPoolStatus('Invalid tip counts JSON')
      return
    }
    setPoolStatus('Saving…')
    savePool.mutate({
      matchId: match.id,
      context: {
        user_points: Number(poolForm.user_points),
        leader_points: Number(poolForm.leader_points),
        remaining_srf_max_points: Number(poolForm.remaining_srf_max_points),
        tip_counts: tipCounts,
      },
    }, {
      onSuccess: () => setPoolStatus('✓ Saved'),
      onError: (e) => setPoolStatus(`Error: ${(e as Error).message}`),
    })
  }

  return (
    <PageTransition>
      <button onClick={() => navigate(-1)} className="mb-4 text-sm font-semibold text-fg-2 hover:text-fg">
        ← Zurück
      </button>

      {/* Header */}
      <header className="mb-6">
        <h1 className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 font-display text-2xl font-extrabold uppercase leading-tight tracking-wide text-fg sm:gap-4 sm:text-4xl">
          <span className="flex min-w-0 items-center gap-2 text-left"><TeamLogo name={match.home_team} src={match.home_logo} /><span className="min-w-0 break-words">{match.home_team}</span></span>
          <span className="text-base text-fg-3 sm:text-xl">vs</span>
          <span className="flex min-w-0 items-center justify-end gap-2 text-right"><span className="min-w-0 break-words">{match.away_team}</span><TeamLogo name={match.away_team} src={match.away_logo} /></span>
        </h1>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Chip>{match.is_ko_phase ? 'K.O. Phase — Punkte ×2' : (match.stage ?? 'League stage')}</Chip>
          {calc && <Chip>xG {calc.xg_home?.toFixed(2) ?? '–'} : {calc.xg_away?.toFixed(2) ?? '–'}</Chip>}
          {h2h && Object.keys(h2h).length > 0 && (
            <Chip>
              H2H {h2h[String(match.home_team_id ?? '')] ?? 0}–{h2h.draws ?? 0}–{h2h[String(match.away_team_id ?? '')] ?? 0}
            </Chip>
          )}
        </div>
      </header>

      {/* Lineup alert */}
      {missing.length > 0 && (
        <GlassCard className="mb-4 border-amber-a/40 bg-amber-a/5">
          <SectionTitle className="mb-2 text-amber-a">Aufstellungs-Alarm</SectionTitle>
          {missing.map(([team, v]) => (
            <p key={team} className="text-sm text-fg-2">
              <b className="text-fg">{team}:</b> fehlend — {v.missing.join(', ')}
            </p>
          ))}
        </GlassCard>
      )}

      <GlassCard className="mb-4 border-emerald-a/30">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="text-xs font-bold uppercase tracking-[0.12em] text-fg-2">Modelltipp</div>
            <div className="display-num mt-1 text-4xl text-fg">{activeTip && activeTip !== 'N/A' ? activeTip : '–'}</div>
          </div>
          {canTip ? (
            <div className="flex flex-col gap-2 sm:min-w-64">
              <button type="button" onClick={copyTip} className="min-h-11 rounded-xl bg-action px-4 py-2.5 text-sm font-bold text-white transition hover:brightness-110">
                Tipp kopieren
              </button>
              <button
                onClick={adopt}
                disabled={saveTip.isPending || !canSaveSharedTip}
                className="min-h-10 rounded-xl border border-line-2 bg-surface px-4 py-2 text-xs font-bold text-fg-2 transition hover:bg-surface-2 disabled:opacity-50"
              >
                {saveTip.isPending ? 'Speichere…' : canSaveSharedTip ? 'Gemeinsamen Spieltipp speichern' : 'Gemeinsamer Tipp geschlossen'}
              </button>
            </div>
          ) : (
            <p className="rounded-xl border border-line bg-surface px-3 py-2 text-sm text-fg-2">
              {fixtureStatus(match, now) === 'pending'
                ? 'Ergebnis ausstehend · Tipps sind geschlossen.'
                : fixtureStatus(match, now) === 'played'
                  ? 'Spiel abgeschlossen · Tipps sind geschlossen.'
                  : 'Anstoßzeit fehlt · Tipp-Aktion geschlossen.'}
            </p>
          )}
        </div>
        <p className="mt-3 text-sm leading-relaxed text-fg-2">
          „Tipp kopieren“ überträgt ihn nicht an den Server. „Gemeinsamen Spieltipp speichern“ schreibt einen zentralen Eintrag für dieses Spiel; er ist derzeit nicht nutzergetrennt.
        </p>
        {copyStatus && <p role="status" className="mt-2 text-xs font-semibold text-emerald-a">{copyStatus}</p>}
        {adoptStatus && <p role="status" className="mt-2 text-xs font-semibold text-fg-2">{adoptStatus}</p>}
      </GlassCard>

      <GlassCard className="mb-4">
        <SectionTitle className="mb-3">Spiel-Einschätzung aus Quoten und Daten</SectionTitle>
        <MatchHintCard match={match} />
      </GlassCard>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* xG + Form */}
        <GlassCard>
          <SectionTitle className="mb-4">Expected Goals & Form</SectionTitle>
          <div className="grid grid-cols-2 gap-4">
            {[
              { team: match.home_team, xg: calc?.xg_home, form: match.home_form },
              { team: match.away_team, xg: calc?.xg_away, form: match.away_form },
            ].map(({ team, xg, form }) => (
              <div key={team} className="text-center">
                <div className="text-sm font-semibold text-fg-2">{flag(team)} {team}</div>
                <div className="display-num mt-1 text-4xl text-emerald-a">{xg?.toFixed(2) ?? '…'}</div>
                <div className="mt-2 flex justify-center"><FormBadges form={form} /></div>
              </div>
            ))}
          </div>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            <TeamFormHistory team={match.home_team} form={match.home_form} />
            <TeamFormHistory team={match.away_team} form={match.away_form} />
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
            <ScoreHeatmap calc={calc} homeDisp={match.home_disp} awayDisp={match.away_disp} />
          ) : (
            <p className="text-sm text-fg-3">{predict.isPending ? 'Rechne…' : 'Keine Daten'}</p>
          )}
        </GlassCard>

        {/* Tip ladder + bots */}
        <GlassCard>
          <SectionTitle className="mb-4">Tipp-Empfehlung</SectionTitle>
          <div className="mb-3 grid gap-2 sm:grid-cols-2">
            <TipSummary label="Model Tipp" tip={modelTip} status={calc?.status ?? match.status} />
            <TipSummary label="Pool Tipp" tip={poolTip} status={calc?.pool_status ?? match.pool_status ?? 'unavailable'} />
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

          <div className="mt-5 border-t border-line pt-4">
            <div className="flex items-center justify-between gap-2">
              <SectionTitle>Pool Context</SectionTitle>
              <button onClick={() => setPoolOpen((open) => !open)} className="text-xs font-semibold text-fg-2 hover:text-fg">
                {poolOpen ? 'Close' : 'Edit'}
              </button>
            </div>
            {!poolOpen && <p className="mt-1 text-xs text-fg-3">{pool.data?.pool_status === 'unavailable' || !pool.data ? 'Pool data unavailable' : `Pool tip: ${pool.data.pool_tip ?? 'unavailable'}`}</p>}
            {poolOpen && (
              <div className="mt-3 grid gap-2 sm:grid-cols-3">
                <NumberField label="Your points" value={poolForm.user_points} onChange={(value) => setPoolForm((v) => ({ ...v, user_points: value }))} />
                <NumberField label="Leader points" value={poolForm.leader_points} onChange={(value) => setPoolForm((v) => ({ ...v, leader_points: value }))} />
                <NumberField label="Remaining max" value={poolForm.remaining_srf_max_points} onChange={(value) => setPoolForm((v) => ({ ...v, remaining_srf_max_points: value }))} />
                <label className="sm:col-span-3 text-xs font-semibold text-fg-2">Tip counts (JSON)
                  <textarea value={poolForm.tip_counts} onChange={(e) => setPoolForm((v) => ({ ...v, tip_counts: e.target.value }))} rows={2} className="mt-1 w-full rounded-lg border border-line bg-surface px-2 py-1.5 font-mono text-xs text-fg outline-none focus:border-emerald-a/50" />
                </label>
                <button onClick={savePoolContext} disabled={savePool.isPending} className="rounded-lg border border-emerald-a/40 bg-emerald-dim px-3 py-2 text-xs font-bold text-emerald-a disabled:opacity-50">{savePool.isPending ? 'Saving…' : 'Save context'}</button>
                {poolStatus && <span className="self-center text-xs text-fg-2">{poolStatus}</span>}
              </div>
            )}
          </div>

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
    </PageTransition>
  )
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className={cn('rounded-full border border-line bg-surface px-3 py-1 text-xs font-semibold text-fg-2')}>
      {children}
    </span>
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

function NumberField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="text-xs font-semibold text-fg-2">{label}<input type="number" min={0} value={value} onChange={(e) => onChange(e.target.value)} className="mt-1 w-full rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-fg outline-none focus:border-emerald-a/50" /></label>
}
