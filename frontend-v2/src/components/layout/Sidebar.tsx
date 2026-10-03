import { NavLink } from 'react-router-dom'
import { useRefreshData } from '../../hooks/queries'
import { useAppState } from '../../state/AppState'
import { cn } from '../../lib/util'

export const PRIMARY_NAV = [
  { to: '/', label: 'Spiele', icon: 'fixtures' },
  { to: '/performance', label: 'Gemeinsame Tipps', icon: 'tips' },
  { to: '/groups', label: 'Tabellen', icon: 'table' },
]
export const MORE_NAV = [
  { to: '/value-bets', label: 'Tipp-Chancen', icon: 'chances', description: 'Spiele nach erwarteten Punkten' },
  { to: '/team-form', label: 'Teams vergleichen', icon: 'teams', description: 'Stärke und bisherige Ergebnisse' },
  { to: '/edge', label: 'Modell & Markt', icon: 'compare', description: 'Unterschiedliche Einschätzungen' },
  { to: '/simulator', label: 'Turnier simulieren', icon: 'trophy', description: 'Mögliche Turnierverläufe' },
]
const ICON_PATHS: Record<string, string> = {
  fixtures: 'M4 5h16v15H4z M8 3v4 M16 3v4 M4 10h16 M8 14h2 M14 14h2',
  tips: 'M5 3h14v18H5z M8 8h8 M8 12h4 M10 16l2 2 4-4',
  table: 'M4 4h16v16H4z M4 9h16 M9 9v11 M4 14h16',
  chances: 'M4 18l5-6 4 3 7-10 M14 5h6v6',
  teams: 'M4 20v-2a4 4 0 0 1 4-4h2a4 4 0 0 1 4 4v2 M17 14a4 4 0 0 1 3 4v2 M12 7a3 3 0 1 1-6 0 3 3 0 0 1 6 0 M17 4a3 3 0 0 1 0 6',
  compare: 'M4 8h15 M15 4l4 4-4 4 M20 16H5 M9 12l-4 4 4 4',
  trophy: 'M8 3h8v6a4 4 0 0 1-8 0z M8 5H4v3a4 4 0 0 0 4 4 M16 5h4v3a4 4 0 0 1-4 4 M12 13v5 M8 21h8 M10 18h4',
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
  const options = competitions.length ? competitions : [{ id: 'wc2026', short_name: 'WM 2026' }, { id: 'ucl2026', short_name: 'UCL 2026/27' }]
  return <label className="competition-select block text-[9px] font-bold uppercase tracking-[0.14em] text-fg-3">Wettbewerb
    <select aria-label="Wettbewerb" value={competition} onChange={e => setCompetition(e.target.value)} className="mt-2.5 min-h-11 w-full rounded border border-line-2 bg-surface px-3 text-xs font-semibold normal-case tracking-normal text-fg">
      {options.map(item => <option key={item.id} value={item.id}>{item.id === 'wc2026' ? 'WM 2026' : item.short_name}</option>)}
    </select>
  </label>
}
export function Settings() {
  const { light, toggleTheme } = useAppState()
  const refresh = useRefreshData()
  return <div className="settings space-y-2">
    <button type="button" onClick={toggleTheme} className="flex min-h-11 w-full items-center justify-between rounded px-3 text-xs text-fg-2 hover:bg-surface-2"><span>Darstellung</span><span className="font-medium text-fg">{light ? 'Hell' : 'Dunkel'}</span></button>
    <button type="button" onClick={() => refresh.mutate()} disabled={refresh.isPending} className="min-h-11 w-full rounded border border-line px-3 text-left text-xs text-fg-2 hover:bg-surface-2 disabled:opacity-50">{refresh.isPending ? 'Wird geladen…' : 'Gespeicherte Daten neu laden'}</button>
    {refresh.isError && <p role="alert" className="px-3 text-xs text-red-a">Daten konnten nicht neu geladen werden. Bitte erneut versuchen.</p>}
    {refresh.isSuccess && <p role="status" className="px-3 text-xs text-fg-3">Gespeicherte Daten geladen.</p>}
  </div>
}
export function Sidebar() {
  return <aside className="app-sidebar sticky top-0 hidden h-dvh shrink-0 flex-col lg:flex">
    <div className="flex h-[85px] shrink-0 items-center px-6"><Brand /></div>
    <div className="min-h-0 flex-1 overflow-y-auto px-4">
      <div className="border-y border-[#304334] px-1 py-6"><CompetitionSelect /></div>
      <nav aria-label="Hauptnavigation" className="space-y-1 pb-6 pt-5">
        <p className="px-3 pb-2 text-[9px] font-bold uppercase tracking-[0.15em] text-[#7f9885]">Spieltag</p>
        {PRIMARY_NAV.map(({ to, label, icon }) => <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => cn('side-nav', isActive && 'active')}><NavIcon name={icon} />{label}</NavLink>)}
        <p className="px-3 pb-2 pt-7 text-[9px] font-bold uppercase tracking-[0.15em] text-[#7f9885]">Analysen</p>
        {MORE_NAV.map(({ to, label, icon }) => <NavLink key={to} to={to} className={({ isActive }) => cn('side-nav', isActive && 'active')}><NavIcon name={icon} />{label}</NavLink>)}
      </nav>
    </div>
    <div className="shrink-0 border-t border-[#304334] p-4">
      <details><summary className="min-h-11 px-3 py-3 text-xs font-medium text-[#b9c7ba]">Einstellungen</summary><Settings /></details>
      <p className="px-3 pb-2 pt-5 text-[9px] leading-relaxed text-[#7f9885]">Football Forecast Lab<br />Von Sajanth Chandrakumar</p>
    </div>
  </aside>
}
