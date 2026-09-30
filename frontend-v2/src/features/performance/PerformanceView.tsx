import { GlassCard, SectionTitle } from '../../components/shared/GlassCard'
import { PageTransition, PageHeader } from '../../components/shared/PageTransition'
import { PerformanceSkeleton } from '../../components/shared/Skeleton'
import { usePerformanceData } from './usePerformanceData'
import { BotScoreboard } from './BotScoreboard'
import { PointsRaceChart } from './PointsRaceChart'
import { BuildABot } from './BuildABot'
import { MatchHistory } from './MatchHistory'

export function PerformanceView() {
  const {
    completed, totals, botStats, extraBots, customBot, simulate, isLoading,
    importPrivateTips, privateTipCount, privateTipPoints,
  } = usePerformanceData()

  if (isLoading) {
    return (
      <PageTransition>
        <PageHeader title="Tipps & Auswertung" subtitle="So haben deine Tipps und das Modell abgeschnitten." />
        <PerformanceSkeleton />
      </PageTransition>
    )
  }

  if (totals.completed === 0) {
    return (
      <PageTransition>
        <PageHeader title="Tipps & Auswertung" subtitle="So haben deine Tipps und das Modell abgeschnitten." />
        <p className="text-fg-2">Noch keine abgeschlossenen Spiele. Die geschützte Wartung synchronisiert Ergebnisse nach Spielende.</p>
      </PageTransition>
    )
  }

  const hitRate = totals.userCount > 0 ? `${((totals.correctTendency / totals.userCount) * 100).toFixed(1)}%` : '—'
  const algoHitRate = totals.algoAllCount > 0 ? ((totals.algoAllTendency / totals.algoAllCount) * 100).toFixed(1) : '0.0'
  const maxPts = Math.max(totals.totalPoints, totals.algoAllTotal, 1)

  const jumpTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })

  return (
    <PageTransition>
      <PageHeader title="Tipps & Auswertung" subtitle="So haben deine Tipps und das Modell abgeschnitten." />

      {/* Quick-nav — one click to every section */}
      <div className="mb-6 flex flex-wrap gap-1.5">
        {[
          ['sec-overview', 'Übersicht'],
          ['sec-bots', 'Bot-Vergleich'],
          ['sec-bob', 'Eigener Bot'],
          ['sec-race', 'Punkteverlauf'],
          ['sec-history', 'Spielverlauf'],
        ].map(([id, label]) => (
          <button
            key={id}
            onClick={() => jumpTo(id)}
            className="rounded-lg border border-line bg-surface px-3.5 py-2 text-xs font-semibold text-fg-2 transition hover:border-emerald-a/40 hover:text-fg"
          >
            {label}
          </button>
        ))}
      </div>

      <div className="space-y-4">
        <GlassCard id="sec-overview" className="scroll-mt-6 !p-0">
          <div className="grid grid-cols-3 divide-x divide-line">
            <Kpi label="Spiele" value={String(totals.completed)} />
            <Kpi label="Deine Punkte" value={String(totals.totalPoints)} />
            <Kpi label="Trefferquote" value={hitRate} />
          </div>
          {totals.userCount === 0 && <p className="border-t border-line px-5 py-3 text-xs text-fg-2">Noch kein eigener Tipp eingetragen. Deine Trefferquote erscheint nach dem ersten ausgewerteten Tipp.</p>}
        </GlassCard>

        {/* You vs Algo */}
        <GlassCard>
          <SectionTitle className="mb-4">Du und das Modell</SectionTitle>
          <div className="mb-4 grid grid-cols-[1fr_auto_1fr] items-center gap-3">
            <div>
              <div className="text-[10px] font-bold uppercase tracking-widest text-gold-a">Du · {totals.userCount} Tipps</div>
              <div className="display-num text-4xl text-gold-a">{totals.totalPoints}</div>
              <div className="text-xs text-fg-3">{hitRate} Tendenz</div>
            </div>
            <div className="text-sm font-extrabold text-fg-2">vs.</div>
            <div className="text-right">
              <div className="text-[10px] font-bold uppercase tracking-widest text-blue-a">Algo · {totals.algoAllCount} Tipps gesamt</div>
              <div className="display-num text-4xl text-blue-a">{totals.algoAllTotal}</div>
              <div className="text-xs text-fg-3">{algoHitRate}% Tendenz über alle eingerechneten Tipps</div>
            </div>
          </div>
          <div className="space-y-2">
            <ScoreBar label="Du" pts={totals.totalPoints} max={maxPts} color="var(--gold)" />
            <ScoreBar label="Algo" pts={totals.algoAllTotal} max={maxPts} color="var(--blue)" />
          </div>
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            <p className="rounded-xl border border-line bg-surface px-3 py-2 text-xs leading-relaxed text-fg-3">
              <span className="font-semibold text-fg-2">Prognosequalität:</span>{' '}
              {totals.brierScore == null ? 'Noch keine verifizierbare Stichprobe.' : `${totals.brierScore.toFixed(3)} Brier-Score`}
              {totals.probabilityCount > 0 && ` · ${totals.probabilityCount} belegte Vorabspiele · kleiner ist besser`}
            </p>
            {totals.legacyCount > 0 && (
              <p className="rounded-xl border border-line bg-surface px-3 py-2 text-xs leading-relaxed text-fg-3">
                <span className="font-semibold text-fg-2">Altbestand (eingerechnet):</span>{' '}
                {totals.legacyCount} ältere Tipps ({totals.legacyPoints} Pts) sind in der Gesamtsumme enthalten, aber nicht als Vorab-Tipps belegbar.
              </p>
            )}
          </div>
          {totals.reconstructedCount > 0 && (
            <p className="mt-4 rounded-xl border border-line bg-surface px-3 py-2 text-xs leading-relaxed text-fg-3">
              Davon: {totals.reconstructedCount} Elo-Rekonstruktionen
              {' '}({totals.reconstructedPoints} Pts · {totals.reconstructedTendency}/{totals.reconstructedCount} Tendenzen).
              {' '}Diese Punkte sind in der Algo-Gesamtsumme enthalten; Rekonstruktionen sind Näherungen ohne historische Buchmacherquoten.
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
            algoPoints={totals.algoAllTotal}
          />
        </div>

        <div id="sec-race" className="scroll-mt-6">
          <PointsRaceChart completed={completed} extraBots={extraBots} />
        </div>

        <div id="sec-history" className="scroll-mt-6">
          <MatchHistory
            completed={completed}
            hasLegacy={totals.hasLegacy}
            hasReconstructed={totals.hasReconstructed}
            privateTipCount={privateTipCount}
            privateTipPoints={privateTipPoints}
            onImportPrivateTips={importPrivateTips}
          />
        </div>
      </div>
    </PageTransition>
  )
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 px-3 py-5 sm:px-6">
      <div className="text-xs font-semibold text-fg-2">{label}</div>
      <div className="mt-2 font-display text-4xl font-bold leading-none tabular-nums text-fg sm:text-5xl">{value}</div>
    </div>
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
