import { useDataStatus } from '../../hooks/queries'
import { useAppState } from '../../state/AppState'
import { competitionLabel } from '../../lib/competition.mjs'
import { formatObservedAt } from '../../lib/observed-at.mjs'
import type { DataStatusDataset, ProviderQuotaStatus } from '../../lib/types'
import { ManualDataRefresh } from '../../components/shared/ManualDataRefresh'
import { PageTransition } from '../../components/shared/PageTransition'
import { QueryState } from '../../components/shared/QueryState'

const PROVIDERS: Record<string, string> = { espn: 'ESPN', clubelo: 'ClubElo', odds_api: 'The Odds API', api_football: 'API-Football', football: 'API-Football', fotmob: 'FotMob', local_elo: 'Lokale Elo-Werte', local: 'Lokaler Datenbestand', derived: 'Aus gespeicherten Ergebnissen' }
const COVERAGE_UNITS: Record<string, string> = { teams: 'Mannschaften', matches: 'Spiele', rows: 'Einträge' }
const observedTime = (value: string | null) => {
  const timestamp = Date.parse(value ?? '')
  return Number.isFinite(timestamp) && timestamp <= Date.now() ? formatObservedAt(value) : 'Zeitpunkt nicht bestätigt'
}
const STATUS: Record<string, string> = { fresh: 'Aktuell erfasst', stale: 'Älterer Datenstand', partial: 'Teilweise erfasst', failed: 'Abruf fehlgeschlagen', unavailable: 'Nicht verfügbar', unknown: 'Nicht bestätigt' }
const providerNames = (providers: string[]) => providers.map(provider => PROVIDERS[provider] ?? provider).join(', ')
const absoluteTime = (value: string | null) => {
  const time = Date.parse(value ?? '')
  return Number.isFinite(time) ? new Intl.DateTimeFormat('de-CH', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Zurich' }).format(time) : 'Nicht erfasst'
}
const allowance = (value: number | null, unit: 'credits' | 'requests') => value == null ? null : `${value.toLocaleString('de-CH')} ${unit === 'credits' ? value === 1 ? 'Credit' : 'Credits' : value === 1 ? 'Abfrage' : 'Abfragen'}`

function DatasetRow({ dataset }: { dataset: DataStatusDataset }) {
  return <article aria-label={dataset.label} className="grid min-w-0 gap-3 border-t border-line py-4 first:border-t-0 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)_minmax(0,1.2fr)]">
    <div className="min-w-0"><h3 className="font-bold text-fg">{dataset.label}</h3>
      {dataset.source_kind === 'derived' && <p className="mt-1 text-xs text-fg-2">Aus gespeicherten Ergebnissen berechnet</p>}
      {dataset.source_kind === 'local' && <p className="mt-1 text-xs text-fg-2">Lokaler Datenbestand</p>}
      {dataset.coverage && <p className="mt-1 text-xs text-fg-2">Abdeckung: {dataset.coverage.available}{dataset.coverage.required != null ? ` von ${dataset.coverage.required}` : ''}{dataset.coverage.unit ? ` ${COVERAGE_UNITS[dataset.coverage.unit]}` : ''}</p>}
    </div>
    <div className="min-w-0 break-words"><p className="text-xs text-fg-3">Erfasste Quelle</p><p className="mt-1 text-sm font-semibold text-fg">{providerNames(dataset.providers.observed) || 'Quelle nicht belegt'}</p>
      {dataset.providers.configured.length > 0 && providerNames(dataset.providers.configured) !== providerNames(dataset.providers.observed) && <p className="mt-1 text-xs text-fg-2">Vorgesehen: {providerNames(dataset.providers.configured)}. Ein Abruf ist dadurch nicht belegt.</p>}
    </div>
    <div className="min-w-0"><p className={`text-sm font-semibold ${dataset.status === 'fresh' ? 'text-emerald-a' : dataset.status === 'failed' ? 'text-red-a' : 'text-amber-a'}`}>{STATUS[dataset.status] ?? 'Nicht bestätigt'}</p>
      <p className="mt-1 text-xs leading-relaxed text-fg-2">{observedTime(dataset.observed_at)}</p>
      {dataset.error && <p className="mt-1 text-xs leading-relaxed text-red-a">{dataset.error}</p>}
      <details className="mt-1 text-xs text-fg-3"><summary className="flex min-h-11 cursor-pointer items-center font-semibold text-accent">Abrufdetails</summary><dl className="space-y-1"><div><dt>Letzter erfasster Versuch</dt><dd>{absoluteTime(dataset.last_attempt_at)}</dd></div><div><dt>Letzter belegter Erfolg</dt><dd>{absoluteTime(dataset.last_successful_at)}</dd></div></dl></details>
    </div>
  </article>
}

function QuotaCard({ name, quota }: { name: string; quota: ProviderQuotaStatus }) {
  const { reported, app_budget: budget } = quota
  const remaining = reported.status === 'unknown' ? null : allowance(reported.remaining, budget.unit)
  return <article aria-label={name} className="surface-panel min-w-0">
    <h3 className="font-bold text-fg">{name}</h3>
    <p className="mt-3 text-xs text-fg-2">Zuletzt vom Anbieter gemeldeter Rest</p>
    <p className="mt-1 text-xl font-bold tabular-nums text-fg">{remaining ?? 'Restkontingent nicht bekannt'}</p>
    <p className="mt-1 text-xs text-fg-3">{observedTime(reported.observed_at)}</p>
    {reported.status !== 'fresh' && <p className="mt-1 text-xs font-semibold text-amber-a">{reported.status === 'stale' ? 'Alter Kontingentstand' : 'Aktualität des Kontingents nicht bestätigt'}</p>}
    {reported.status !== 'unknown' && reported.used != null && <p className="mt-2 text-xs text-fg-2">Vom Anbieter als verbraucht gemeldet: {allowance(reported.used, budget.unit)}{reported.limit != null ? ` von ${reported.limit}` : ''}</p>}
    <div className="mt-4 border-t border-line pt-3"><h4 className="text-sm font-semibold text-fg">Gemeinsames App-Budget</h4>
      <p className="mt-1 text-xs text-fg-2">{budget.window_seconds === 2678400 ? 'Rollierende 31 Tage' : budget.window_seconds === 86400 ? 'Rollierende 24 Stunden' : `${budget.window_seconds / 3600} Stunden`}</p>
      {budget.status === 'available' && budget.used != null && budget.remaining != null ? <><p className="mt-2 font-bold tabular-nums text-fg">{allowance(budget.remaining, budget.unit)} im App-Budget frei</p><p className="mt-1 text-xs text-fg-2">{allowance(budget.used, budget.unit)} von {budget.limit} reserviert</p></> : <p className="mt-2 text-sm text-fg-2">App-Verbrauch nicht bekannt</p>}
      <p className="mt-2 text-xs leading-relaxed text-fg-3">Die Anbieterreserve von {allowance(budget.headroom, budget.unit)} kann Abrufe früher begrenzen. Fehlgeschlagene Versuche zählen im App-Budget mit.</p>
    </div>
  </article>
}

export function DataSourcesView() {
  const { competition, competitions } = useAppState()
  const query = useDataStatus()
  const data = query.data
  return <PageTransition>
    <header className="page-header"><div><h1 className="page-title">API &amp; Daten</h1><p className="page-description">Datenquellen für {competitionLabel(competition, competitions)}</p></div>
      <button type="button" disabled={query.isFetching} onClick={() => { void query.refetch() }} className="min-h-11 rounded-lg border border-line-2 bg-surface px-4 text-sm font-semibold text-fg disabled:opacity-50">Übersicht neu laden</button>
    </header>
    <p className="mb-5 max-w-prose text-sm leading-relaxed text-fg-2">Hier siehst du den gespeicherten Stand. Das Öffnen oder Neuladen dieser Übersicht löst keine Anbieterabfragen aus.</p>
    {query.isPending && <p role="status" className="surface-panel">Datenübersicht wird geladen…</p>}
    {query.isError && !data && <QueryState title="Datenübersicht nicht verfügbar" message="Die gespeicherten Quellen und Kontingente konnten nicht geladen werden." onRetry={() => { void query.refetch() }} />}
    {query.isError && data && <p role="alert" className="mb-4 rounded-lg border border-amber-a bg-surface p-4 text-sm text-fg-2">Die Datenübersicht konnte nicht aktualisiert werden. Der letzte bekannte Stand bleibt sichtbar.</p>}
    {data && <div className="space-y-5">
      <section aria-label="Datenquellen" className="analysis-section"><h2 className="text-lg font-bold text-fg">Quellen &amp; Datenstand</h2><div className="mt-2">{data.datasets.map(dataset => <DatasetRow key={dataset.id} dataset={dataset} />)}</div></section>
      <section aria-label="Gemeinsame Anbieter-Kontingente" className="analysis-section"><h2 className="text-lg font-bold text-fg">Anbieter-Kontingente</h2><p className="mt-1 text-sm font-semibold text-fg-2">Gemeinsam für WM, UCL und PL</p><p className="mt-2 text-xs leading-relaxed text-fg-3">Anbieterstand und App-Budget sind getrennte Zähler. Bei The Odds API werden Credits gezählt; ein Abruf kann mehrere Credits verbrauchen.</p>
        <div className="mt-4 grid gap-3 md:grid-cols-2"><QuotaCard name="The Odds API" quota={data.quotas.providers.odds} /><QuotaCard name="API-Football" quota={data.quotas.providers.football} /></div><p className="mt-3 text-xs leading-relaxed text-fg-3">Für ESPN und ClubElo ist kein Restkontingent erfasst. Auch für mögliche FotMob-Fallbacks liegt kein Restzähler vor; das bedeutet kein unbegrenztes Kontingent.</p>
      </section>
      <section aria-label="Wartungsstatus" className="analysis-section"><h2 className="text-lg font-bold text-fg">Automatische Datenpflege</h2><p className="mt-2 text-sm font-semibold text-fg">{data.maintenance.running ? 'Wartung läuft' : data.maintenance.status === 'success' ? 'Letzte Wartung abgeschlossen' : data.maintenance.status === 'partial' ? 'Letzte Wartung teilweise erfolgreich' : data.maintenance.status === 'failed' ? 'Letzte Wartung fehlgeschlagen' : 'Kein bestätigter Wartungslauf erfasst'}</p>
        <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-3">{[['Letzter Versuch', data.maintenance.last_run_at], ['Letzter vollständiger Erfolg', data.maintenance.last_successful_at], ['Nächste fällige Prüfung', data.maintenance.next_due_at]].map(([label, value]) => <div key={label}><dt className="text-xs text-fg-3">{label}</dt><dd className="mt-1 font-semibold text-fg">{absoluteTime(value)}</dd></div>)}</dl>
        {data.maintenance.error && <p className="mt-3 text-xs text-amber-a">{data.maintenance.error}</p>}<p className="mt-3 text-xs leading-relaxed text-fg-3">Prüfzeitpunkte sind keine Garantie für neue Anbieterdaten. Auf dem kostenlosen Hosting kann der Dienst schlafen.</p>
      </section>
    </div>}
    <section aria-label="Anbieterdaten aktualisieren" className="analysis-section mt-5"><h2 className="mb-3 text-lg font-bold text-fg">Daten aktualisieren</h2><p className="mb-3 text-sm leading-relaxed text-fg-2">Der Sofortabruf für PL und UCL lädt Anbieter innerhalb der vorhandenen Kontingente. Das Ergebnis nennt den tatsächlichen Erfolg je Datenquelle.</p><ManualDataRefresh /></section>
  </PageTransition>
}
