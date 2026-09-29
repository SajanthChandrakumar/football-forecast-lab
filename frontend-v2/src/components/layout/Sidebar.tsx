import { NavLink } from 'react-router-dom'
import { useQuota, useRefreshData } from '../../hooks/queries'
import { useAppState } from '../../state/AppState'
import { Switch } from '../ui/Switch'
import { cn } from '../../lib/util'
import { competitionLabel } from '../../lib/competition.mjs'

const NAV = [
  { to: '/', icon: '▦', label: 'Spiele' },
  { to: '/performance', icon: '◈', label: 'Meine Tipps' },
]

const MORE_NAV = [
  { to: '/value-bets', icon: '↑', label: 'Tipp-Chancen' },
  { to: '/edge', icon: '⇄', label: 'Modellvergleich' },
  { to: '/team-form', icon: '∿', label: 'Teamvergleich' },
  { to: '/groups', icon: '▤', label: 'Tabelle' },
  { to: '/simulator', icon: '🎲', label: 'K.O. Simulator' },
]

function QuotaMeter() {
  const { data } = useQuota()
  const rows = [
    { label: 'Odds API', q: data?.odds },
    { label: 'Football API', q: data?.football },
  ]
  return (
    <div className="glass space-y-3 p-3.5">
      {rows.map(({ label, q }) => {
        const remaining = Number(q?.remaining)
        const used = Number(q?.used)
        const total = Number.isFinite(remaining) && Number.isFinite(used) ? remaining + used : null
        const pct = total ? (remaining / total) * 100 : 0
        return (
          <div key={label}>
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-fg-3">{label}</span>
              <span className="text-right">
                <span className="display-num text-lg text-fg">{q?.remaining ?? '…'}</span>
                <span className="ml-1 text-[10px] text-fg-3">/ {q?.used ?? '…'} used</span>
              </span>
            </div>
            <div className="mt-1 h-1 overflow-hidden rounded-full bg-surface-2">
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${pct}%`,
                  background: pct > 30 ? 'var(--emerald)' : pct > 10 ? 'var(--amber)' : 'var(--red)',
                }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

function SidebarButtons() {
  const refresh = useRefreshData()

  return (
    <div className="space-y-2">
      <button
        onClick={() => refresh.mutate()}
        disabled={refresh.isPending}
        className="min-h-11 w-full rounded-xl px-4 py-2.5 text-sm font-bold text-white transition hover:brightness-110 disabled:opacity-50"
        style={{
          background: 'var(--cobalt)',
        }}
      >
        {refresh.isPending ? 'Lade…' : 'Gespeicherte Spiele neu laden'}
      </button>
    </div>
  )
}

export function Sidebar() {
  const { competition, setCompetition, competitions, competitionsLoading, light, toggleTheme } = useAppState()
  return (
    <aside className="hidden w-64 shrink-0 flex-col gap-5 border-r border-line bg-surface p-5 lg:flex">
      {/* Brand */}
      <div className="rounded-2xl bg-[#193b2b] px-3 py-3">
        <span className="block truncate font-display text-lg font-bold text-[#f8f7f2]">
          Football Forecast Lab
        </span>
        <span className="mt-1 block text-[10px] leading-4 text-[#cbdccf]">
          {competitionLabel(competition, competitions)} · Statistische Fussballprognosen und transparente Modellanalyse.
        </span>
      </div>

      <nav>
        <div className="mb-2 text-xs font-bold uppercase tracking-[0.12em] text-fg-2">Übersicht</div>
        <ul className="space-y-1">
          {NAV.map(({ to, icon, label }) => (
            <li key={to}>
              <NavLink
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  cn(
                    'relative flex min-h-11 items-center gap-3 rounded-xl px-3 py-2 text-sm font-semibold transition',
                    isActive
                      ? 'bg-emerald-dim text-fg'
                      : 'text-fg-2 hover:bg-surface hover:text-fg',
                  )
                }
              >
                <span className="w-4 text-center text-emerald-a/80">{icon}</span>
                {label}
              </NavLink>
            </li>
          ))}
        </ul>
        <details className="mt-3 border-t border-line pt-3">
          <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between rounded-xl px-3 text-sm font-semibold text-fg-2 hover:bg-surface-2 [&::-webkit-details-marker]:hidden">
            Weitere Ansichten <span aria-hidden="true">⌄</span>
          </summary>
          <ul className="mt-1 space-y-1">
            {MORE_NAV.map(({ to, icon, label }) => (
              <li key={to}>
                <NavLink to={to} className={({ isActive }) => cn('flex min-h-11 items-center gap-3 rounded-xl px-3 py-2 text-sm font-semibold', isActive ? 'bg-emerald-dim text-fg' : 'text-fg-2 hover:bg-surface-2 hover:text-fg')}>
                  <span className="w-4 text-center text-emerald-a/80">{icon}</span>{label}
                </NavLink>
              </li>
            ))}
          </ul>
        </details>
      </nav>

      <div>
        <div className="mb-2 text-xs font-bold uppercase tracking-[0.12em] text-fg-2">Wettbewerb</div>
        <label className="flex cursor-pointer items-center justify-between gap-2 rounded-xl px-3 py-2 hover:bg-surface">
          <span>
            <span className="block text-sm font-bold text-fg">{competitionLabel(competition, competitions)}</span>
            <span className="block text-xs text-fg-3">{competitionsLoading ? 'Lädt…' : 'Spiele und Auswertung'}</span>
          </span>
          <select
            aria-label="Wettbewerb"
            value={competition}
            onChange={(e) => setCompetition(e.target.value)}
            className="max-w-24 rounded-lg border border-line bg-surface px-2 py-1 text-xs font-semibold text-fg outline-none focus:border-emerald-a/50"
          >
            {(competitions.length ? competitions : [
              { id: 'wc2026', short_name: 'WC 2026', display_name: 'World Cup 2026' },
              { id: 'ucl2026', short_name: 'UCL 2026/27', display_name: 'Champions League 2026/27' },
            ]).map((item) => <option key={item.id} value={item.id}>{item.short_name}</option>)}
          </select>
        </label>
      </div>

      <div>
        <div className="mb-2 text-xs font-bold uppercase tracking-[0.12em] text-fg-2">Darstellung</div>
        <label className="flex cursor-pointer items-center justify-between gap-2 rounded-xl px-3 py-2 hover:bg-surface">
          <span>
            <span className="block text-sm font-bold text-fg">Helles Design</span>
            <span className="block text-[11px] text-fg-3">Hell oder dunkel</span>
          </span>
          <Switch checked={light} onCheckedChange={toggleTheme} />
        </label>
      </div>

      <div className="mt-auto max-lg:mt-2 space-y-3">
        <details className="border-t border-line pt-3">
          <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between rounded-xl px-3 text-sm font-semibold text-fg-2 hover:bg-surface-2 [&::-webkit-details-marker]:hidden">
            Datenstatus <span aria-hidden="true">⌄</span>
          </summary>
          <div className="space-y-3 pt-2"><QuotaMeter /><SidebarButtons /></div>
        </details>
        <a
          href="https://github.com/SajanthChandrakumar"
          target="_blank"
          rel="noopener noreferrer"
          className="group flex items-center justify-between gap-2 rounded-xl border border-emerald-a/25 bg-surface p-2.5 text-[11px] font-medium text-fg-2 transition-all hover:border-emerald-a/50 hover:bg-emerald-dim/60 hover:text-fg"
        >
          <div className="flex min-w-0 items-center gap-2">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-dim text-[10px] font-bold text-emerald-a">
              SC
            </span>
            <div className="truncate">
              <span className="block text-[9px] font-bold uppercase tracking-wider text-fg-3 group-hover:text-emerald-a/80">
                Engineered by
              </span>
              <span className="truncate font-semibold text-fg">Sajanth Chandrakumar</span>
            </div>
          </div>
          <span className="text-fg-3 transition-transform group-hover:translate-x-0.5 group-hover:text-emerald-a">
            ↗
          </span>
        </a>
      </div>
    </aside>
  )
}
