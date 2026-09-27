import { useEffect, useRef, useState, type RefObject } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useRefreshData } from '../../hooks/queries'
import { useAppState } from '../../state/AppState'
import { cn } from '../../lib/util'
import { Sidebar } from './Sidebar'

const PRIMARY_NAV = [
  { to: '/', label: 'Spiele', icon: '▦' },
  { to: '/performance', label: 'Meine Tipps', icon: '◈' },
] as const

const MORE_NAV = [
  { to: '/value-bets', label: 'Top Value Bets' },
  { to: '/edge', label: 'Model Edge' },
  { to: '/team-form', label: 'Team Form' },
  { to: '/groups', label: 'Groups' },
  { to: '/simulator', label: 'K.-o.-Simulator' },
] as const

function MobileMoreMenu({ open, onClose, menuRef }: {
  open: boolean
  onClose: () => void
  menuRef: RefObject<HTMLDivElement | null>
}) {
  const { competition, setCompetition, competitions, light, toggleTheme } = useAppState()
  const refresh = useRefreshData()
  if (!open) return null

  const options = competitions.length ? competitions : [
    { id: 'wc2026' as const, short_name: 'WM 2026', display_name: 'World Cup 2026' },
    { id: 'ucl2026' as const, short_name: 'UCL 2026/27', display_name: 'Champions League 2026/27' },
  ]

  return (
    <div
      id="mobile-more-menu"
      ref={menuRef}
      role="dialog"
      aria-modal="true"
      className="fixed inset-x-3 bottom-[4.75rem] z-40 max-h-[calc(100vh-8rem)] overflow-y-auto rounded-2xl border border-line bg-surface p-4 shadow-2xl lg:hidden"
      aria-label="Weitere Ansichten und Einstellungen"
      tabIndex={-1}
    >
      <nav aria-label="Weitere Ansichten" className="grid gap-1">
        {MORE_NAV.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onClose}
            className={({ isActive }) => cn(
              'flex min-h-11 items-center rounded-xl px-3 text-sm font-semibold transition',
              isActive ? 'bg-emerald-dim text-emerald-a' : 'text-fg-2 hover:bg-surface-2 hover:text-fg',
            )}
          >
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="mt-4 space-y-2 border-t border-line pt-4">
        <label className="flex min-h-11 items-center justify-between gap-3 rounded-xl px-3 text-sm text-fg-2">
          <span>Wettbewerb</span>
          <select
            aria-label="Wettbewerb"
            value={competition}
            onChange={(event) => setCompetition(event.target.value as 'wc2026' | 'ucl2026')}
            className="min-h-11 max-w-36 rounded-lg border border-line bg-surface-2 px-2 text-sm font-semibold text-fg outline-none focus:border-emerald-a"
          >
            {options.map((item) => <option key={item.id} value={item.id}>{item.short_name}</option>)}
          </select>
        </label>
        <button
          type="button"
          onClick={toggleTheme}
          className="flex min-h-11 w-full items-center justify-between rounded-xl px-3 text-left text-sm text-fg-2 hover:bg-surface-2 hover:text-fg"
        >
          <span>Darstellung</span>
          <span className="font-semibold text-fg">{light ? 'Hell' : 'Dunkel'}</span>
        </button>
        <button
          type="button"
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending}
          className="flex min-h-11 w-full items-center justify-between rounded-xl bg-emerald-a px-3 text-left text-sm font-bold text-white transition hover:brightness-110 disabled:opacity-50"
        >
          <span>{refresh.isPending ? 'Lade…' : 'Gespeicherte Spiele neu laden'}</span>
          <span aria-hidden>↻</span>
        </button>
      </div>
    </div>
  )
}

function MobileTopBar() {
  const { competition } = useAppState()
  return (
    <header className="flex min-h-14 items-center border-b border-line bg-surface px-4 lg:hidden">
      <div className="flex min-w-0 items-center gap-2.5">
        <span className="rounded-lg bg-emerald-a px-2 py-1 text-xs font-black text-white">
          {competition === 'ucl2026' ? 'UCL' : 'WM'}
        </span>
        <span className="truncate font-display text-lg font-extrabold text-fg">2026 Predictor</span>
      </div>
    </header>
  )
}

function MobileBottomNav({ onMore, moreOpen, moreButtonRef, onNavigate }: {
  onMore: () => void
  moreOpen: boolean
  moreButtonRef: RefObject<HTMLButtonElement | null>
  onNavigate: () => void
}) {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-50 grid grid-cols-3 border-t border-line bg-surface p-2 shadow-[0_-8px_24px_-20px_rgba(15,23,42,0.8)] lg:hidden" aria-label="Hauptnavigation">
      {PRIMARY_NAV.map(({ to, label, icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          onClick={onNavigate}
          className={({ isActive }) => cn(
            'flex min-h-12 flex-col items-center justify-center gap-0.5 rounded-xl text-[11px] font-bold transition',
            isActive ? 'bg-emerald-dim text-emerald-a' : 'text-fg-3 hover:bg-surface-2 hover:text-fg',
          )}
        >
          <span className="text-base" aria-hidden>{icon}</span>
          {label}
        </NavLink>
      ))}
      <button
        type="button"
        onClick={onMore}
        ref={moreButtonRef}
        aria-controls="mobile-more-menu"
        aria-expanded={moreOpen}
        className={cn(
          'flex min-h-12 flex-col items-center justify-center gap-0.5 rounded-xl text-[11px] font-bold transition',
          moreOpen ? 'bg-emerald-dim text-emerald-a' : 'text-fg-3 hover:bg-surface-2 hover:text-fg',
        )}
      >
        <span className="text-base" aria-hidden>•••</span>
        Mehr
      </button>
    </nav>
  )
}

export function AppShell() {
  const [moreOpen, setMoreOpen] = useState(false)
  const moreButtonRef = useRef<HTMLButtonElement>(null)
  const moreMenuRef = useRef<HTMLDivElement>(null)
  const toggleMore = () => setMoreOpen((open) => !open)
  const closeMore = () => setMoreOpen(false)

  useEffect(() => {
    if (!moreOpen) return
    moreMenuRef.current?.focus()
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      setMoreOpen(false)
      requestAnimationFrame(() => moreButtonRef.current?.focus())
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [moreOpen])

  return (
    <div className="min-h-screen bg-bg lg:flex">
      <Sidebar />
      <div className="min-w-0 flex-1">
        <MobileTopBar />
        <main className="min-w-0 flex-1 px-4 pb-24 pt-5 sm:p-6 sm:pb-24 lg:p-8">
          <div className="mx-auto max-w-6xl">
            <Outlet />
          </div>
        </main>
      </div>
      <MobileMoreMenu open={moreOpen} onClose={closeMore} menuRef={moreMenuRef} />
      <MobileBottomNav onMore={toggleMore} moreOpen={moreOpen} moreButtonRef={moreButtonRef} onNavigate={closeMore} />
    </div>
  )
}
