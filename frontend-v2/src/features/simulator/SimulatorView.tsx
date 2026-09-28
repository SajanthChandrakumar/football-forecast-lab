import { motion } from 'framer-motion'
import { useKnockoutSimulation } from '../../hooks/queries'
import { useAppState } from '../../state/AppState'
import { flag, cn } from '../../lib/util'
import { GlassCard, SectionTitle } from '../../components/shared/GlassCard'
import { PageTransition, PageHeader, staggerContainer, staggerItem } from '../../components/shared/PageTransition'
import type { KnockoutSimulation, UclSimulation } from '../../lib/types'
import { hasUclSimulationResults } from '../../lib/simulation.mjs'
import { ChartSkeleton } from '../../components/shared/Skeleton'

const COLUMNS: { key: 'reached_qf' | 'reached_sf' | 'reached_final' | 'champion'; label: string; color: string }[] = [
  { key: 'reached_qf', label: 'Viertelfinale', color: 'var(--blue)' },
  { key: 'reached_sf', label: 'Halbfinale', color: 'var(--purple)' },
  { key: 'reached_final', label: 'Finale', color: 'var(--amber)' },
  { key: 'champion', label: 'Champion', color: 'var(--gold)' },
]

export function SimulatorView() {
  const { data, isLoading, error } = useKnockoutSimulation()
  const { competition } = useAppState()

  if (competition === 'ucl2026') {
    return <UclSimulator data={data as UclSimulation | undefined} isLoading={isLoading} error={error as Error | null} />
  }
  const wcData = data as KnockoutSimulation | undefined

  return (
    <PageTransition>
      <PageHeader
        title="K.O. Simulator"
        subtitle="Monte-Carlo-Simulation ab dem Achtelfinale — reine Elo-Wahrscheinlichkeiten, keine Marktdaten (noch keine Quoten für hypothetische Spätrunden)"
      />

      {isLoading && (
        <div className="space-y-4">
          <p className="text-fg-2">Simuliere Turnierverläufe…</p>
          <ChartSkeleton />
        </div>
      )}
      {error && <p className="text-red-a">Fehler: {(error as Error).message}</p>}

      {wcData && (
        <div className="space-y-4">
          <GlassCard className="!p-0">
            <div className="flex items-center justify-between border-b border-line px-5 py-4">
              <SectionTitle>Titelchancen</SectionTitle>
              <span className="text-xs text-fg-3">{wcData.n_runs.toLocaleString('de-CH')} simulierte Turniere</span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[10px] font-bold uppercase tracking-wider text-fg-3">
                    <th className="px-5 py-2 text-left">#</th>
                    <th className="px-2 py-2 text-left">Team</th>
                    <th className="px-2 py-2 text-right">Elo</th>
                    {COLUMNS.map((c) => (
                      <th key={c.key} className="px-4 py-2 text-left max-sm:hidden" style={{ minWidth: 140 }}>
                        {c.label}
                      </th>
                    ))}
                    <th className="px-5 py-2 text-right sm:hidden">Champ.</th>
                  </tr>
                </thead>
                <tbody>
                  {wcData.results.map((r, i) => (
                    <tr key={r.team} className={cn('border-t border-line', i === 0 && 'bg-gold-dim/30')}>
                      <td className="px-5 py-2.5 tabular-nums text-fg-3">{i + 1}</td>
                      <td className="px-2 py-2.5 font-semibold text-fg">
                        {flag(r.team)} <span className="ml-1">{r.team}</span>
                      </td>
                      <td className="display-num px-2 py-2.5 text-right text-fg">{Math.round(r.elo)}</td>
                      {COLUMNS.map((c) => (
                        <td key={c.key} className="px-4 py-2.5 max-sm:hidden">
                          <PctCell value={r[c.key]} color={c.color} />
                        </td>
                      ))}
                      <td className="px-5 py-2.5 text-right sm:hidden">
                        <span className="display-num text-gold-a">{r.champion.toFixed(1)}%</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </GlassCard>

          <GlassCard>
            <SectionTitle className="mb-3">Bracket — Achtelfinale</SectionTitle>
            <p className="mb-4 text-xs text-fg-3">
              Ausgangspunkt der Simulation. Der weitere Baum (Viertelfinale, Halbfinale, Finale) ergibt sich aus den Siegern.
            </p>
            <motion.div variants={staggerContainer} initial="initial" animate="animate" className="grid gap-2 sm:grid-cols-2">
              {wcData.bracket.map((m, i) => (
                <motion.div
                  key={i}
                  variants={staggerItem}
                  className="flex items-center justify-between rounded-lg border border-line bg-surface px-3 py-2 text-sm"
                >
                  <span className="font-semibold text-fg">{flag(m.home)} {m.home}</span>
                  <span className="text-fg-3">vs</span>
                  <span className="font-semibold text-fg">{m.away} {flag(m.away)}</span>
                </motion.div>
              ))}
            </motion.div>
          </GlassCard>
        </div>
      )}
    </PageTransition>
  )
}

function UclSimulator({ data, isLoading, error }: { data?: UclSimulation; isLoading: boolean; error: Error | null }) {
  const hasResults = hasUclSimulationResults(data)
  return (
    <PageTransition>
      <PageHeader title="Turnier-Simulator" subtitle="Eine experimentelle Orientierung auf Basis des gespeicherten Spielmodells." />
      {isLoading && <p className="text-fg-2">Turnierverläufe werden berechnet…</p>}
      {error && <p className="text-red-a">Simulation fehlgeschlagen: {error.message}</p>}
      {data?.status === 'unavailable' && <p className="text-amber-a">Simulation derzeit nicht verfügbar: {data.error || data.reason || data.warnings?.join(' ') || 'Modelldaten fehlen'}</p>}
      {hasResults && data && <div className="space-y-4">
        {data.warnings?.length ? <GlassCard><SectionTitle className="mb-2">Datenlage</SectionTitle><ul className="space-y-1 text-xs text-fg-2">{data.warnings.map((warning) => <li key={warning}>• {warning}</li>)}</ul></GlassCard> : null}
        <GlassCard className="!p-0">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-5 py-4"><SectionTitle>Simulationsergebnisse</SectionTitle><span className="text-xs text-fg-3">{(data.n_runs ?? data.runs ?? 0).toLocaleString('de-CH')} Durchläufe · Startwert {data.seed ?? '—'}</span></div>
          <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="text-[10px] font-bold uppercase tracking-wider text-fg-3">
            {['#', 'Team', 'Ø Pkt', 'Ø Rank', 'Top 8', 'Top 24', 'R16', 'QF', 'SF', 'Final', 'Champion'].map((label) => <th key={label} className="whitespace-nowrap px-3 py-2 text-right first:text-left">{label}</th>)}
          </tr></thead><tbody>{data.results.map((team, index) => <tr key={team.team} className={cn('border-t border-line', index === 0 && 'bg-gold-dim/30')}>
            <td className="px-3 py-2 tabular-nums text-fg-3">{index + 1}</td><td className="px-3 py-2 text-left font-semibold text-fg">{flag(team.team)} {team.team}</td>
            <td className="px-3 py-2 text-right tabular-nums text-fg-2">{team.expected_points.toFixed(2)}</td><td className="px-3 py-2 text-right tabular-nums text-fg-2">{team.expected_rank.toFixed(2)}</td>
            {(['top8', 'top24', 'round_of_16', 'quarterfinal', 'semifinal', 'final', 'champion'] as const).map((key) => <td key={key} className="px-3 py-2 text-right tabular-nums text-fg-2">{team[key].toFixed(1)}%</td>)}
          </tr>)}</tbody></table></div>
        </GlassCard>
        {data.bracket && <GlassCard><SectionTitle className="mb-3">Bracket and provenance</SectionTitle><p className="mb-3 text-xs text-fg-3">Ranking source: {data.ranking_source ?? 'local'} · table {data.table_version ?? '—'} · coefficients {data.coefficient_version ?? '—'}</p><BracketValue value={data.bracket} /></GlassCard>}
      </div>}
    </PageTransition>
  )
}

function BracketValue({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value == null || typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return <span className="text-xs text-fg-2">{String(value ?? '—')}</span>
  if (Array.isArray(value)) return <div className="space-y-2 pl-3">{value.map((item, index) => <div key={index} className="rounded-lg border border-line bg-surface p-2"><BracketValue value={item} depth={depth + 1} /></div>)}</div>
  return <div className="space-y-2">{Object.entries(value as Record<string, unknown>).map(([key, item]) => <div key={key} className="text-xs"><span className="font-bold text-fg">{key.replaceAll('_', ' ')}:</span> <BracketValue value={item} depth={depth + 1} /></div>)}</div>
}

function PctCell({ value, color }: { value: number; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-surface-2">
        <div className="h-full rounded-full transition-all" style={{ width: `${value}%`, background: color }} />
      </div>
      <span className="w-12 shrink-0 text-right text-xs font-semibold tabular-nums" style={{ color }}>
        {value.toFixed(1)}%
      </span>
    </div>
  )
}
