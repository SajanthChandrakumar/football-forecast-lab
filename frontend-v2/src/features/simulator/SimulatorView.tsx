import { useKnockoutSimulation } from '../../hooks/queries'
import { useAppState } from '../../state/AppState'
import { cn } from '../../lib/util'
import { TeamLogo } from '../../components/shared/Badges'
import { GlassCard, SectionTitle } from '../../components/shared/GlassCard'
import { PageTransition, PageHeader } from '../../components/shared/PageTransition'
import { QueryState } from '../../components/shared/QueryState'
import type { KnockoutSimulation, UclSimulation, UclSimulationTeam } from '../../lib/types'
import { hasUclSimulationResults } from '../../lib/simulation.mjs'
import { ChartSkeleton } from '../../components/shared/Skeleton'

const WC_COLUMNS = [
  { key: 'reached_qf', label: 'Viertelfinale' },
  { key: 'reached_sf', label: 'Halbfinale' },
  { key: 'reached_final', label: 'Finale' },
  { key: 'champion', label: 'Titel' },
] as const

const UCL_COLUMNS = [
  { key: 'top8', label: 'Top 8' },
  { key: 'top24', label: 'Top 24' },
  { key: 'round_of_16', label: 'Achtelfinale' },
  { key: 'quarterfinal', label: 'Viertelfinale' },
  { key: 'semifinal', label: 'Halbfinale' },
  { key: 'final', label: 'Finale' },
  { key: 'champion', label: 'Titel' },
] as const

export function SimulatorView() {
  const query = useKnockoutSimulation()
  const { competition } = useAppState()

  if (competition === 'ucl2026') {
    return <UclSimulator data={query.data as UclSimulation | undefined} isLoading={query.isLoading} error={query.error as Error | null} onRetry={() => void query.refetch()} />
  }
  if (competition !== 'wc2026') {
    return <PageTransition><PageHeader title="Turnier-Simulator" subtitle="Mögliche Turnierverläufe." /><p className="text-sm text-fg-2">Für diesen Wettbewerb ist noch keine Simulation eingerichtet.</p></PageTransition>
  }

  const wcData = query.data as KnockoutSimulation | undefined
  return (
    <PageTransition>
      <PageHeader title="K.-o.-Simulation" subtitle="Die Simulation startet bei den Achtelfinal-Paarungen. Die vorherigen Runden stehen bereits fest." />
      {query.isLoading && <div className="space-y-3"><p className="text-sm text-fg-2">Turnierverläufe werden berechnet…</p><ChartSkeleton /></div>}
      {query.error && <QueryState title="Simulation fehlgeschlagen" message="Die Turnierchancen konnten nicht geladen werden." onRetry={() => void query.refetch()} />}
      {!query.isLoading && !query.error && !wcData && <QueryState title="Keine Simulation verfügbar" message="Es liegen keine berechneten Turnierchancen vor." onRetry={() => void query.refetch()} />}

      {wcData && !query.error && <div className="space-y-4">
        <GlassCard>
          <SectionTitle className="mb-2">Was die Zahlen zeigen</SectionTitle>
          <p className="text-sm leading-relaxed text-fg-2">
            Grundlage sind die aktuellen Elo-Werte mit Gastgeberbonus. Für hypothetische spätere Paarungen liegen keine Quoten vor. Die Prozentwerte stammen aus {wcData.n_runs.toLocaleString('de-CH')} Durchläufen.
          </p>
        </GlassCard>

        <GlassCard className="!p-0">
          <div className="border-b border-line px-5 py-4"><SectionTitle>Titelchancen je Team</SectionTitle></div>
          <div className="overflow-x-auto" role="region" aria-label="Titel- und Rundenchancen" tabIndex={0}>
            <table className="w-full min-w-[680px] text-sm">
              <thead><tr className="text-left text-xs font-medium text-fg-2">
                <th scope="col" className="px-5 py-3">Team</th><th scope="col" className="px-3 py-3 text-right">Elo</th>
                {WC_COLUMNS.map(({ key, label }) => <th scope="col" key={key} className="px-3 py-3 text-right">Erreicht {label}</th>)}
              </tr></thead>
              <tbody>{wcData.results.map((row) => <tr key={row.team} className="border-t border-line">
                <th scope="row" className="px-5 py-3 text-left font-semibold text-fg"><span className="inline-flex items-center gap-2"><TeamLogo name={row.team} />{row.team}</span></th>
                <td className="px-3 py-3 text-right tabular-nums text-fg-2">{Math.round(row.elo)}</td>
                {WC_COLUMNS.map(({ key }) => <td key={key} className={cn('px-3 py-3 text-right tabular-nums', key === 'champion' ? 'font-semibold text-fg' : 'text-fg-2')}>{row[key].toFixed(1)}%</td>)}
              </tr>)}</tbody>
            </table>
          </div>
        </GlassCard>

        <GlassCard>
          <SectionTitle className="mb-1">Startpaarungen</SectionTitle>
          <p className="mb-4 text-sm text-fg-2">Aus diesen Achtelfinal-Spielen entwickelt sich der weitere Turnierbaum.</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {wcData.bracket.map((match) => <div key={`${match.home}-${match.away}`} className="flex items-center justify-between gap-3 rounded-lg border border-line bg-surface px-3 py-2.5 text-sm">
              <span className="inline-flex min-w-0 items-center gap-2 font-medium text-fg"><TeamLogo name={match.home} /><span className="truncate">{match.home}</span></span>
              <span aria-hidden="true" className="text-fg-3">–</span>
              <span className="inline-flex min-w-0 items-center gap-2 font-medium text-fg"><span className="truncate">{match.away}</span><TeamLogo name={match.away} /></span>
            </div>)}
          </div>
        </GlassCard>
      </div>}
    </PageTransition>
  )
}

function UclSimulator({ data, isLoading, error, onRetry }: { data?: UclSimulation; isLoading: boolean; error: Error | null; onRetry: () => void }) {
  const hasResults = hasUclSimulationResults(data)
  const runs = data?.n_runs ?? data?.runs ?? 0
  const results = [...(data?.results ?? [])].sort((a, b) => a.team.localeCompare(b.team, 'de'))
  return (
    <PageTransition>
      <PageHeader title="Turnier-Simulation" subtitle="Modellrechnung für den weiteren Verlauf der UCL-Ligaphase und K.-o.-Runden." />
      {isLoading && <p className="text-sm text-fg-2">Turnierverläufe werden berechnet…</p>}
      {error && <QueryState title="Simulation fehlgeschlagen" message="Die Turnierchancen konnten nicht geladen werden." onRetry={onRetry} />}
      {!isLoading && !error && data?.status === 'unavailable' && <QueryState title="Simulation derzeit nicht verfügbar" message="Für die Berechnung fehlen aktuell notwendige Modelldaten." />}
      {!isLoading && !error && hasResults && data && data.results.length === 0 && <QueryState title="Keine Ergebnisse verfügbar" message="Die Simulation hat keine Teamresultate geliefert." onRetry={onRetry} />}

      {hasResults && data && data.results.length > 0 && !error && <div className="space-y-4">
        <GlassCard>
          <SectionTitle className="mb-2">Einordnung</SectionTitle>
          <p className="text-sm leading-relaxed text-fg-2">
            Grundlage sind {runs.toLocaleString('de-CH')} simulierte Turnierverläufe. {runs <= 1_000 ? 'Das ist eine kleine Stichprobe: Die Werte sind grobe Orientierung, und kleine Abstände oder die Reihenfolge sind nicht stabil.' : 'Die Werte sind Modellschätzungen, keine Vorhersage sicherer Ergebnisse.'}
            {' '}Prozentwerte sind auf ganze Prozentpunkte gerundet.
          </p>
          {data.warnings?.length ? <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-fg-2">{[...new Set(data.warnings)].map((warning) => <li key={warning}>{translateWarning(warning)}</li>)}</ul> : null}
        </GlassCard>

        <GlassCard className="!p-0">
          <div className="border-b border-line px-5 py-4"><SectionTitle>Ergebnisse je Team</SectionTitle></div>
          <div className="overflow-x-auto" role="region" aria-label="UCL-Simulationsergebnisse je Team" tabIndex={0}>
            <table className="w-full min-w-[920px] text-sm">
              <thead><tr className="text-left text-xs font-medium text-fg-2">
                <th scope="col" className="px-5 py-3">Team</th><th scope="col" className="px-3 py-3 text-right">Punkte im Schnitt</th><th scope="col" className="px-3 py-3 text-right">Rang im Schnitt</th>
                {UCL_COLUMNS.map(({ key, label }) => <th scope="col" key={key} className="px-3 py-3 text-right">{label}</th>)}
              </tr></thead>
              <tbody>{results.map((team: UclSimulationTeam) => <tr key={team.team} className="border-t border-line">
                <th scope="row" className="px-5 py-3 text-left font-semibold text-fg"><span className="inline-flex items-center gap-2"><TeamLogo name={team.team} />{team.team}</span></th>
                <td className="px-3 py-3 text-right tabular-nums text-fg-2">{team.expected_points.toFixed(1)}</td><td className="px-3 py-3 text-right tabular-nums text-fg-2">{team.expected_rank.toFixed(1)}</td>
                {UCL_COLUMNS.map(({ key }) => <td key={key} className="px-3 py-3 text-right tabular-nums text-fg-2">{Math.round(team[key])}%</td>)}
              </tr>)}</tbody>
            </table>
          </div>
        </GlassCard>

        <details className="rounded-xl border border-line bg-surface px-5 py-4">
          <summary className="cursor-pointer text-sm font-medium text-fg">Datenquellen und Rechenstand</summary>
          <p className="mt-3 text-sm leading-relaxed text-fg-2">
            Tabellenstand: {data.table_version ?? 'nicht angegeben'} · Koeffizienten: {data.coefficient_version ?? 'nicht angegeben'} · Ranglistenquelle: {data.ranking_source === 'local' ? 'lokale Berechnung' : data.ranking_source ?? 'nicht angegeben'}.
          </p>
        </details>
      </div>}
    </PageTransition>
  )
}

function translateWarning(warning: string) {
  if (warning.includes('UEFA coefficient input unavailable')) return 'UEFA-Koeffizienten fehlen. Bei sonst gleich bewerteten Teams entscheidet als letzter Ersatz die alphabetische Reihenfolge.'
  if (warning.includes('UEFA coefficient coverage incomplete')) return 'UEFA-Koeffizienten liegen nicht für alle Teams vor. Bei sonst gleich bewerteten Teams bleibt die alphabetische Reihenfolge als letzter Ersatz.'
  if (warning.includes('ESPN official order unavailable')) return 'Die offizielle Reihenfolge ist nicht verfügbar; die Simulation nutzt eine lokale Sortierung.'
  return 'Ein Teil der Modelldaten fehlt; die Simulation verwendet verfügbare Ersatzwerte.'
}
