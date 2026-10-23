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
import { ViewTabs, ViewPanel } from '../../components/shared/ViewTabs'
import { useView } from '../../hooks/useView'

const SIMULATION_VIEWS = ['titles', 'rounds'] as const

const SIMULATION_TABS = [
  { value: 'titles', label: 'Titelchancen' },
  { value: 'rounds', label: 'Alle Runden' },
] as const

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
  const [view, setView] = useView(SIMULATION_VIEWS, 'titles')
  const query = useKnockoutSimulation()
  const { competition } = useAppState()

  if (competition === 'ucl2026') {
    return <UclSimulator
      data={query.data as UclSimulation | undefined}
      isLoading={query.isLoading}
      error={query.error as Error | null}
      onRetry={() => void query.refetch()}
      view={view}
      onViewChange={setView}
    />
  }
  if (competition === 'epl2026') {
    return <PageTransition><PageHeader title="K.-o.-Simulator" subtitle="Für die Premier League nicht anwendbar." /><p className="text-sm text-fg-2">Der K.-o.-Simulator bildet keine Ligatabelle oder Saison ab.</p></PageTransition>
  }
  if (competition !== 'wc2026') {
    return <PageTransition><PageHeader title="Turnier-Simulator" subtitle="Mögliche Turnierverläufe." /><p className="text-sm text-fg-2">Für diesen Wettbewerb ist noch keine Simulation eingerichtet.</p></PageTransition>
  }

  const wcData = query.data as KnockoutSimulation | undefined
  const hasWcResults = Boolean(wcData?.results?.length) && wcData?.status !== 'unavailable'
  return (
    <PageTransition>
      <PageHeader title="K.-o.-Simulation" subtitle="Die Simulation startet bei den Achtelfinal-Paarungen. Die vorherigen Runden stehen bereits fest." />
      {hasWcResults && wcData && !query.error && <WcSimulationSummary data={wcData} />}
      {query.isLoading && <div className="analysis-section space-y-3"><p className="text-sm text-fg-2">Turnierverläufe werden berechnet…</p><ChartSkeleton /></div>}
      {query.error && <QueryState title="Simulation fehlgeschlagen" message="Die Turnierchancen konnten nicht geladen werden." onRetry={() => void query.refetch()} />}
      {!query.isLoading && !query.error && !hasWcResults && <QueryState title="Keine Simulation verfügbar" message="Es liegen keine berechneten Turnierchancen vor." onRetry={() => void query.refetch()} />}

      <ViewTabs id="simulation" label="Simulationsansicht" items={SIMULATION_TABS} value={view} onChange={setView} />
      <ViewPanel id="simulation" value="titles" active={view}>
        {hasWcResults && wcData && !query.error && <TitleChanceList results={wcData.results} precision={1} />}
      </ViewPanel>
      <ViewPanel id="simulation" value="rounds" active={view}>
        {hasWcResults && wcData && !query.error && <div className="analysis-section space-y-4">
          <GlassCard className="surface-panel !p-0">
            <div className="border-b border-line px-5 py-4"><SectionTitle>Ergebnisse je Team</SectionTitle></div>
            <div className="overflow-x-auto" role="region" aria-label="Titel- und Rundenchancen" tabIndex={0}>
              <table className="w-full min-w-[680px] text-sm">
                <thead><tr className="bg-surface-2 text-left text-xs font-bold text-fg">
                  <th scope="col" className="px-5 py-3">Team</th><th scope="col" className="px-3 py-3 text-right">Elo</th>
                  {WC_COLUMNS.map(({ key, label }) => <th scope="col" key={key} className="px-3 py-3 text-right">Erreicht {label}</th>)}
                </tr></thead>
                <tbody>{wcData.results.map((row) => <tr key={row.team} className="border-t border-line">
                  <th scope="row" className="px-5 py-3 text-left font-semibold text-fg"><span className="inline-flex items-center gap-2"><TeamLogo name={row.team} />{row.team}</span></th>
                  <td className="px-3 py-3 text-right tabular-nums text-fg-2">{Math.round(row.elo)}</td>
                  {WC_COLUMNS.map(({ key }) => <td key={key} className={cn('px-3 py-3 text-right tabular-nums', key === 'champion' ? 'ranking-points font-bold text-fg' : 'text-fg-2')}>{row[key].toFixed(1)}%</td>)}
                </tr>)}</tbody>
              </table>
            </div>
          </GlassCard>

          <GlassCard className="surface-panel">
            <SectionTitle className="section-heading mb-1">Startpaarungen</SectionTitle>
            <p className="mb-4 text-sm text-fg-2">Aus diesen Achtelfinal-Spielen entwickelt sich der weitere Turnierbaum.</p>
            <div className="match-grid grid gap-2 sm:grid-cols-2">
              {wcData.bracket.map((match) => <div key={`${match.home}-${match.away}`} className="match-card surface-panel flex items-center justify-between gap-3 rounded-lg border border-line bg-surface px-3 py-2.5 text-sm">
                <span className="inline-flex min-w-0 items-center gap-2 font-medium text-fg"><TeamLogo name={match.home} /><span className="truncate">{match.home}</span></span>
                <span aria-hidden="true" className="text-fg-3">–</span>
                <span className="inline-flex min-w-0 items-center gap-2 font-medium text-fg"><span className="truncate">{match.away}</span><TeamLogo name={match.away} /></span>
              </div>)}
            </div>
          </GlassCard>
        </div>}
      </ViewPanel>
    </PageTransition>
  )
}

function WcSimulationSummary({ data }: { data: KnockoutSimulation }) {
  return <GlassCard className="surface-panel analysis-section">
    <SectionTitle className="section-heading mb-2">Simulation · {data.n_runs.toLocaleString('de-CH')} Durchläufe</SectionTitle>
    <p className="text-sm leading-relaxed text-fg-2">
      Grundlage sind die aktuellen Elo-Werte mit Gastgeberbonus. Für hypothetische spätere Paarungen liegen keine Quoten vor. Die Prozentwerte stammen aus {data.n_runs.toLocaleString('de-CH')} Durchläufen.
    </p>
    {data.n_runs <= 1_000 && <p className="mt-3 rounded-lg border border-amber-a/30 bg-amber-a/5 px-3 py-2 text-sm text-fg-2">Kleine Stichprobe: Die Werte sind grobe Orientierung; kleine Abstände oder die Reihenfolge sind nicht stabil.</p>}
    {data.warnings?.length ? <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-fg-2">{[...new Set(data.warnings)].map((warning) => <li key={warning}>{translateWarning(warning)}</li>)}</ul> : null}
  </GlassCard>
}

function UclSimulator({ data, isLoading, error, onRetry, view, onViewChange }: {
  data?: UclSimulation
  isLoading: boolean
  error: Error | null
  onRetry: () => void
  view: typeof SIMULATION_VIEWS[number]
  onViewChange: (view: typeof SIMULATION_VIEWS[number]) => void
}) {
  const hasResults = hasUclSimulationResults(data)
  const runs = data?.n_runs ?? data?.runs ?? 0
  const results = [...(data?.results ?? [])].sort((a, b) => a.team.localeCompare(b.team, 'de'))
  return (
    <PageTransition>
      <PageHeader title="Turnier-Simulation" subtitle="Modellrechnung für den weiteren Verlauf der UCL-Ligaphase und K.-o.-Runden." />
      {hasResults && data && <GlassCard className="surface-panel analysis-section">
        <SectionTitle className="section-heading mb-2">Simulation · {runs.toLocaleString('de-CH')} Durchläufe</SectionTitle>
        <p className="text-sm leading-relaxed text-fg-2">
          Grundlage sind {runs.toLocaleString('de-CH')} simulierte Turnierverläufe. {runs <= 1_000 ? 'Das ist eine kleine Stichprobe: Die Werte sind grobe Orientierung, und kleine Abstände oder die Reihenfolge sind nicht stabil.' : 'Die Werte sind Modellschätzungen, keine Vorhersage sicherer Ergebnisse.'}
          {' '}Prozentwerte sind auf ganze Prozentpunkte gerundet.
        </p>
        {data.warnings?.length ? <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-fg-2">{[...new Set(data.warnings)].map((warning) => <li key={warning}>{translateWarning(warning)}</li>)}</ul> : null}
        <details className="info-disclosure mt-3"><summary>Datenquellen und Rechenstand</summary>
          <p className="info-content">Tabellenstand: {data.table_version ?? 'nicht angegeben'} · Koeffizienten: {data.coefficient_version ?? 'nicht angegeben'} · Ranglistenquelle: {data.ranking_source === 'local' ? 'lokale Berechnung' : data.ranking_source ?? 'nicht angegeben'}.</p>
        </details>
      </GlassCard>}
      {isLoading && <p className="analysis-section text-sm text-fg-2">Turnierverläufe werden berechnet…</p>}
      {error && <QueryState title="Simulation fehlgeschlagen" message="Die Turnierchancen konnten nicht geladen werden." onRetry={onRetry} />}
      {!isLoading && !error && data?.status === 'unavailable' && <QueryState title="Simulation derzeit nicht verfügbar" message="Für die Berechnung fehlen aktuell notwendige Modelldaten." />}
      {!isLoading && !error && hasResults && data && data.results.length === 0 && <QueryState title="Keine Ergebnisse verfügbar" message="Die Simulation hat keine Teamresultate geliefert." onRetry={onRetry} />}

      <ViewTabs id="simulation" label="Simulationsansicht" items={SIMULATION_TABS} value={view} onChange={onViewChange} />
      <ViewPanel id="simulation" value="titles" active={view}>
        {hasResults && data && data.results.length > 0 && !error && <TitleChanceList results={data.results} />}
      </ViewPanel>
      <ViewPanel id="simulation" value="rounds" active={view}>
        {hasResults && data && data.results.length > 0 && !error && <GlassCard className="surface-panel !p-0">
          <div className="border-b border-line px-5 py-4"><SectionTitle>Ergebnisse je Team</SectionTitle></div>
          <div className="overflow-x-auto" role="region" aria-label="UCL-Simulationsergebnisse je Team" tabIndex={0}>
            <table className="w-full min-w-[920px] text-sm">
              <thead><tr className="bg-surface-2 text-left text-xs font-bold text-fg">
                <th scope="col" className="px-5 py-3">Team</th><th scope="col" className="px-3 py-3 text-right">Punkte im Schnitt</th><th scope="col" className="px-3 py-3 text-right">Rang im Schnitt</th>
                {UCL_COLUMNS.map(({ key, label }) => <th scope="col" key={key} className="px-3 py-3 text-right">{label}</th>)}
              </tr></thead>
              <tbody>{results.map((team: UclSimulationTeam) => <tr key={team.team} className="border-t border-line">
                <th scope="row" className="px-5 py-3 text-left font-semibold text-fg"><span className="inline-flex items-center gap-2"><TeamLogo name={team.team} />{team.team}</span></th>
                <td className="px-3 py-3 text-right tabular-nums text-fg-2">{team.expected_points.toFixed(1)}</td><td className="px-3 py-3 text-right tabular-nums text-fg-2">{team.expected_rank.toFixed(1)}</td>
                {UCL_COLUMNS.map(({ key }) => <td key={key} className={cn('px-3 py-3 text-right tabular-nums', key === 'champion' ? 'ranking-points font-bold text-fg' : 'text-fg-2')}>{Math.round(team[key])}%</td>)}
              </tr>)}</tbody>
            </table>
          </div>
        </GlassCard>}
      </ViewPanel>
    </PageTransition>
  )
}

function TitleChanceList({ results, precision = 0 }: { results: Array<{ team: string; champion: number }>; precision?: 0 | 1 }) {
  const sorted = [...results].sort((a, b) => b.champion - a.champion || a.team.localeCompare(b.team, 'en'))
  return <section className="analysis-section" aria-label="Titelchancen">
    <h2 className="section-heading">Titelchancen je Team</h2>
    <ol className="ranking-list" aria-label="Titelchancen nach Wahrscheinlichkeit">
      {sorted.map(({ team, champion }) => <li key={team} className="ranking-row surface-panel">
        <span className="ranking-team inline-flex min-w-0 items-center gap-3"><TeamLogo name={team} /><span className="truncate font-semibold text-fg">{team}</span></span>
        <strong className="ranking-points tabular-nums font-bold text-fg">{champion.toFixed(precision)}%</strong>
        <span className="chance-track" aria-hidden="true"><span className="chance-fill" style={{ width: `${Math.max(0, Math.min(100, champion))}%` }} /></span>
      </li>)}
    </ol>
  </section>
}

function translateWarning(warning: string) {
  if (warning.includes('UEFA coefficient input unavailable')) return 'UEFA-Koeffizienten fehlen. Bei sonst gleich bewerteten Teams entscheidet als letzter Ersatz die alphabetische Reihenfolge.'
  if (warning.includes('UEFA coefficient coverage incomplete')) return 'UEFA-Koeffizienten liegen nicht für alle Teams vor. Bei sonst gleich bewerteten Teams bleibt die alphabetische Reihenfolge als letzter Ersatz.'
  if (warning.includes('ESPN official order unavailable')) return 'Die offizielle Reihenfolge ist nicht verfügbar; die Simulation nutzt eine lokale Sortierung.'
  return 'Ein Teil der Modelldaten fehlt; die Simulation verwendet verfügbare Ersatzwerte.'
}
