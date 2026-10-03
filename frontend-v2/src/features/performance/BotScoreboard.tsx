import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { GlassCard, SectionTitle } from '../../components/shared/GlassCard'
import { cn } from '../../lib/util'
import { HOUSE_BOTS, type PerformanceTotals, type ScoreRow } from './usePerformanceData'
import type { BotKey } from '../../lib/types'

export function BotScoreboard({ totals, botStats, extraBots }: {
  totals: PerformanceTotals
  botStats: Record<BotKey, { pts: number; tipped: number; tendency: number }>
  extraBots: ScoreRow[]
}) {
  const [showStrategies, setShowStrategies] = useState(false)

  const rows = useMemo<ScoreRow[]>(() => {
    const out: ScoreRow[] = [
      {
        key: 'shared', label: 'Gemeinsame Tipps', color: 'var(--blue)', isUser: true,
        pts: totals.totalPoints, tipped: totals.userCount, tendency: totals.correctTendency,
      },
      ...HOUSE_BOTS.filter((b) => botStats[b.key].tipped > 0).map((b) => ({
        key: b.key, label: b.label, color: b.color, ...botStats[b.key],
      })),
      ...extraBots.filter((bot) => bot.tipped > 0),
    ]
    return out.sort((a, b) => (b.pts / Math.max(b.tipped, 1)) - (a.pts / Math.max(a.tipped, 1)))
  }, [totals, botStats, extraBots])

  return (
    <GlassCard className="!p-0">
      <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
        <SectionTitle>Bot-Punktestand</SectionTitle>
        <button
          type="button"
          aria-expanded={showStrategies}
          onClick={() => setShowStrategies((v) => !v)}
          className="rounded-lg border border-line bg-surface px-3 py-1.5 text-xs font-semibold text-fg-2 transition hover:bg-surface-2"
        >
          {showStrategies ? 'Schließen' : 'Wie funktionieren die Strategien?'}
        </button>
      </div>

      <div className="overflow-x-auto">
        <p className="px-5 pb-2 text-xs leading-relaxed text-fg-3">
          Sortiert nach Punkten pro Spiel. Die Zahl der ausgewerteten Spiele kann je Strategie abweichen.
        </p>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] font-bold uppercase tracking-wider text-fg-3">
              <th className="px-5 py-2 text-left">Strategie</th>
              <th className="px-2 py-2 text-right">Punkte</th>
              <th className="px-2 py-2 text-right max-sm:hidden">Spiele</th>
              <th className="px-2 py-2 text-right">Punkte/Spiel</th>
              <th className="px-5 py-2 text-right">Tendenz</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.key} className={cn('border-t border-line', r.isUser && 'bg-blue-a/5')}>
                <td className="px-5 py-2.5">
                  <span className="mr-2 text-fg-3">{i + 1}.</span>
                  <span className={cn('font-bold')} style={{ color: r.color }}>{r.label}</span>
                </td>
                <td className="display-num px-2 py-2.5 text-right text-base" style={{ color: r.color }}>{r.pts}</td>
                <td className="px-2 py-2.5 text-right tabular-nums text-fg-2 max-sm:hidden">{r.tipped}</td>
                <td className="px-2 py-2.5 text-right tabular-nums text-fg-2">
                  {r.tipped > 0 ? (r.pts / r.tipped).toFixed(2) : '—'}
                </td>
                <td className="px-5 py-2.5 text-right tabular-nums text-fg-3">
                  {r.tipped > 0 ? `${Math.round((r.tendency / r.tipped) * 100)}%` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <AnimatePresence>
        {showStrategies && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className="overflow-hidden border-t border-line"
          >
            <div className="space-y-3 p-5">
              <Strategy icon="A" title="Modell — Die Standardstrategie">
                <b>70 % Buchmacherquoten + 30 % Elo-Wertungen</b>; daraus entstehen Torwahrscheinlichkeiten.
                Die gewählte Prognose erzielt im Punktesystem den höchsten Erwartungswert.
              </Strategy>
              <Strategy icon="B" title="Broker — Buchmacherquoten">
                <b>100 % Markt, 0 % Elo.</b> Nutzt ausschliesslich Buchmacherquoten.
              </Strategy>
              <Strategy icon="P" title="Professor — Elo-Wertungen">
                <b>100 % Elo, 0 % Markt.</b> Nutzt ausschliesslich Elo-Wertungen.
              </Strategy>
              <Strategy icon="X" title="X-Sniper — Unentschieden-Spezialist">
                Wählt immer ein <b>Unentschieden</b>, wenn es den höchsten Erwartungswert hat.
              </Strategy>
              <Strategy icon="Z" title="Zocker — Gewichteter Zufall">
                Wählt zufällig aus den <b>zehn Tipps mit höchstem Erwartungswert</b>.
              </Strategy>
              <div className="rounded-xl border border-dashed border-line bg-surface p-3 text-xs leading-relaxed text-fg-3">
                <b className="text-fg-2">Punktesystem:</b> Exakter Spielstand = <b>10 Punkte</b> ·
                Richtige Tordifferenz = <b>8 Punkte</b> · Richtige Tendenz = <b>5 Punkte</b> · Falsch = <b>0 Punkte</b>.
                In der K.O.-Phase verdoppeln sich die Punkte (×2).
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </GlassCard>
  )
}

function Strategy({ icon, title, children }: {
  icon: string; title: string; children: React.ReactNode
}) {
  return (
    <div className="flex gap-3">
      <span
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-line text-xs font-semibold text-fg-2"
      >
        {icon}
      </span>
      <div>
        <div className="text-sm font-semibold text-fg">{title}</div>
        <div className="text-xs leading-relaxed text-fg-2">{children}</div>
      </div>
    </div>
  )
}
