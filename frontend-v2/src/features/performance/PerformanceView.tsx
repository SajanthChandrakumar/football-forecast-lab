import { GlassCard, SectionTitle } from '../../components/shared/GlassCard'
import { PageTransition, PageHeader } from '../../components/shared/PageTransition'
import { PerformanceSkeleton } from '../../components/shared/Skeleton'
import { usePerformanceData } from './usePerformanceData'
import { BotScoreboard } from './BotScoreboard'
import { PointsRaceChart } from './PointsRaceChart'
import { BuildABot } from './BuildABot'
import { MatchHistory } from './MatchHistory'

export function PerformanceView() {
  const { completed, totals, botStats, extraBots, customBot, simulate, isLoading } = usePerformanceData()

  if (isLoading) {
    return (
      <PageTransition>
        <PageHeader title="Algorithm Performance" subtitle="Prediction accuracy vs actual results" />
        <PerformanceSkeleton />
      </PageTransition>
    )
  }

  if (totals.completed === 0) {
    return (
      <PageTransition>
        <PageHeader title="Algorithm Performance" subtitle="Prediction accuracy vs actual results" />
        <p className="text-fg-2">Noch keine abgeschlossenen Spiele. Die geschützte Wartung synchronisiert Ergebnisse nach Spielende.</p>
      </PageTransition>
    )
  }

  const hitRate = totals.userCount > 0 ? ((totals.correctTendency / totals.userCount) * 100).toFixed(1) : '0.0'
  const algoHitRate = totals.algoCount > 0 ? ((totals.algoTendency / totals.algoCount) * 100).toFixed(1) : '0.0'
  const maxPts = Math.max(totals.totalPoints, totals.algoTotal, 1)

  const jumpTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })

  return (
    <PageTransition>
      <PageHeader title="Algorithm Performance" subtitle="Prediction accuracy vs actual results" />

      {/* Quick-nav — one click to every section */}
      <div className="mb-6 flex flex-wrap gap-1.5">
        {[
          ['sec-overview', 'Übersicht'],
          ['sec-bots', 'Bot Scoreboard'],
          ['sec-bob', 'Build a Bot'],
          ['sec-race', 'Points Race'],
          ['sec-history', 'Match History'],
        ].map(([id, label]) => (
          <button
            key={id}
            onClick={() => jumpTo(id)}
            className="rounded-full border border-line bg-surface px-3.5 py-1.5 text-xs font-semibold text-fg-2 transition hover:border-emerald-a/40 hover:text-fg"
          >
            {label}
          </button>
        ))}
      </div>

      <div className="space-y-4">
        {/* KPI cards */}
        <div id="sec-overview" className="grid scroll-mt-6 gap-4 sm:grid-cols-3">
          <Kpi label="Completed Matches" value={String(totals.completed)} color="var(--text-1)" />
          <Kpi label="Total SRF Points" value={String(totals.totalPoints)} color="var(--emerald)" />
          <Kpi label="Hit Rate (Tendenz)" value={`${hitRate}%`} color="var(--gold)" />
        </div>

        {/* You vs Algo */}
        <GlassCard>
          <SectionTitle className="mb-4">You vs Algo</SectionTitle>
          <div className="mb-4 grid grid-cols-[1fr_auto_1fr] items-center gap-3">
            <div>
              <div className="text-[10px] font-bold uppercase tracking-widest text-gold-a">Du · {totals.userCount} Tipps</div>
              <div className="display-num text-4xl text-gold-a">{totals.totalPoints}</div>
              <div className="text-xs text-fg-3">{hitRate}% Tendenz</div>
            </div>
            <div className="text-sm font-extrabold text-fg-2">vs.</div>
            <div className="text-right">
              <div className="text-[10px] font-bold uppercase tracking-widest text-blue-a">Algo · {totals.algoCount} Vorab-Tipps</div>
              <div className="display-num text-4xl text-blue-a">{totals.algoTotal}</div>
              <div className="text-xs text-fg-3">{algoHitRate}% Tendenz</div>
            </div>
          </div>
          <div className="space-y-2">
            <ScoreBar label="Du" pts={totals.totalPoints} max={maxPts} color="var(--gold)" />
            <ScoreBar label="Algo" pts={totals.algoTotal} max={maxPts} color="var(--blue)" />
          </div>
          {totals.reconstructedCount > 0 && (
            <p className="mt-4 rounded-xl border border-line bg-surface px-3 py-2 text-xs leading-relaxed text-fg-3">
              Zusätzlich: {totals.reconstructedCount} Elo-Rekonstruktionen
              {' '}({totals.reconstructedPoints} Pts · {totals.reconstructedTendency}/{totals.reconstructedCount} Tendenzen).
              {' '}Rekonstruktionen sind Näherungen ohne historische Buchmacherquoten.
            </p>
          )}
        </GlassCard>

        <div id="sec-bots" className="scroll-mt-6">
          <BotScoreboard totals={totals} botStats={botStats} extraBots={extraBots} />
        </div>

        <div id="sec-bob" className="scroll-mt-6">
          <BuildABot
            customBot={customBot}
            simulate={simulate}
            userPoints={totals.totalPoints}
            algoPoints={totals.algoTotal}
          />
        </div>

        <div id="sec-race" className="scroll-mt-6">
          <PointsRaceChart completed={completed} extraBots={extraBots} />
        </div>

        <div id="sec-history" className="scroll-mt-6">
          <MatchHistory completed={completed} hasReconstructed={totals.hasReconstructed} />
        </div>
      </div>
    </PageTransition>
  )
}

function Kpi({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <GlassCard className="relative overflow-hidden">
      <div
        className="pointer-events-none absolute -right-8 -top-8 h-28 w-28 rounded-full opacity-20 blur-2xl"
        style={{ background: color }}
      />
      <div className="text-[10px] font-bold uppercase tracking-[0.15em] text-fg-3">{label}</div>
      <div className="display-num mt-1 text-6xl" style={{ color, textShadow: `0 0 32px color-mix(in srgb, ${color} 35%, transparent)` }}>
        {value}
      </div>
    </GlassCard>
  )
}

function ScoreBar({ label, pts, max, color }: { label: string; pts: number; max: number; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-10 text-right text-[11px] font-bold" style={{ color }}>{label}</span>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
        <div className="h-full rounded-full transition-all" style={{ width: `${(pts / max) * 100}%`, background: color }} />
      </div>
      <span className="w-14 text-xs tabular-nums text-fg-2">{pts} Pts</span>
    </div>
  )
}
