import { competitionLabel } from '../../lib/competition.mjs'
import { useRefreshData } from '../../hooks/queries'
import { useAppState } from '../../state/AppState'
import { NavLink } from 'react-router-dom'

export const PRIMARY_NAV = [
  { to: '/', label: 'Spiele', icon: 'fixtures' },
  { to: '/performance', label: 'Gemeinsame Tipps', icon: 'tips' },
  { to: '/groups', label: 'Tabellen', icon: 'table' },
]
export const MORE_NAV = [
  { to: '/data-sources', label: 'API & Daten', icon: 'data', description: 'Quellen, Aktualität und Kontingente' },
  { to: '/value-bets', label: 'Tipp-Chancen', icon: 'chances', description: 'Spiele nach erwarteten Punkten' },
  { to: '/team-form', label: 'Teams vergleichen', icon: 'teams', description: 'Stärke und bisherige Ergebnisse' },
  { to: '/edge', label: 'Modell & Markt', icon: 'compare', description: 'Unterschiedliche Einschätzungen' },
  { to: '/simulator', label: 'Turnier simulieren', icon: 'trophy', description: 'Mögliche Turnierverläufe' },
]
const COMPETITION_BUTTONS = [
  { id: 'wc2026', name: 'WM', title: 'Weltmeisterschaft 2026' },
  { id: 'ucl2026', name: 'UCL', title: 'UEFA Champions League 2026/27' },
  { id: 'epl2026', name: 'PL', title: 'Premier League 2026/27' },
] as const
const ICON_PATHS: Record<string, string> = {
  fixtures: 'M4 5h16v15H4z M8 3v4 M16 3v4 M4 10h16 M8 14h2 M14 14h2',
  tips: 'M5 3h14v18H5z M8 8h8 M8 12h4 M10 16l2 2 4-4',
  table: 'M4 4h16v16H4z M4 9h16 M9 9v11 M4 14h16',
  chances: 'M4 18l5-6 4 3 7-10 M14 5h6v6',
  teams: 'M4 20v-2a4 4 0 0 1 4-4h2a4 4 0 0 1 4 4v2 M17 14a4 4 0 0 1 3 4v2 M12 7a3 3 0 1 1-6 0 3 3 0 0 1 6 0 M17 4a3 3 0 0 1 0 6',
  compare: 'M4 8h15 M15 4l4 4-4 4 M20 16H5 M9 12l-4 4 4 4',
  trophy: 'M8 3h8v6a4 4 0 0 1-8 0z M8 5H4v3a4 4 0 0 0 4 4 M16 5h4v3a4 4 0 0 1-4 4 M12 13v5 M8 21h8 M10 18h4',
  data: 'M5 5h14v14H5z M5 10h14 M10 10v9 M14 5v5',
  more: 'M5 12h1 M11.5 12h1 M18 12h1',
}
export function NavIcon({ name, className = 'h-[18px] w-[18px]' }: { name: string; className?: string }) {
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className}><path d={ICON_PATHS[name] ?? ICON_PATHS.more} /></svg>
}
export function Brand() {
  return <span className="brand"><span className="brand-mark"><svg aria-hidden="true" viewBox="0 0 24 24" className="h-6 w-6" fill="currentColor"><path d="M5 4h15v4H9v3h8v4H9v6H5z" /><path d="M13 18h7v3h-7z" /></svg></span><span className="brand-name">Forecast Lab<span>Football intelligence</span></span></span>
}
export function CompetitionSelect() {
  const { competition, setCompetition, competitions } = useAppState()
  const standardIds = new Set<string>(COMPETITION_BUTTONS.map(({ id }) => id))
  const additional = competitions.filter(item => !standardIds.has(item.id))
  return <div role="group" aria-label="Wettbewerb" className="competition-select">
    {COMPETITION_BUTTONS.map(item => <button key={item.id} type="button" aria-label={item.name} title={item.title} aria-pressed={competition === item.id} onClick={() => setCompetition(item.id)} className="competition-option">{item.name}</button>)}
    {additional.map(item => <button key={item.id} type="button" aria-label={item.short_name} title={item.display_name} aria-pressed={competition === item.id} onClick={() => setCompetition(item.id)} className="competition-option">{item.short_name}</button>)}
  </div>
}
export function Settings({ showDataLink = true }: { showDataLink?: boolean }) {
  const { light, toggleTheme, competitions } = useAppState()
  const refresh = useRefreshData()
  return <div className="settings space-y-2">
    <button type="button" aria-pressed={!light} onClick={toggleTheme} className="flex min-h-11 w-full items-center justify-between rounded px-3 text-xs text-fg-2 hover:bg-surface-2"><span>Darstellung</span><span className="font-medium text-fg">{light ? 'Hell' : 'Dunkel'}</span></button>
    {showDataLink && <NavLink to="/data-sources" className="flex min-h-11 items-center rounded border border-line px-3 text-xs font-semibold text-accent hover:bg-surface-2">API &amp; Daten · Quellen und Aktualisierung</NavLink>}
    <button type="button" onClick={() => refresh.mutate()} disabled={refresh.isPending} className="min-h-11 w-full rounded border border-line px-3 text-left text-xs text-fg-2 hover:bg-surface-2 disabled:opacity-50">{refresh.isPending ? 'Wird geladen…' : 'Gespeicherte Daten neu laden'}</button>
    {refresh.isError && <p role="alert" className="px-3 text-xs text-red-a">Daten konnten nicht neu geladen werden. Bitte erneut versuchen.</p>}
    {refresh.isSuccess && <p role="status" className="px-3 text-xs text-fg-3">Gespeicherte Daten für {competitionLabel(refresh.data.competition, competitions)} geladen.</p>}
  </div>
}
