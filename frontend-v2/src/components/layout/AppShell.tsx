import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigationType } from 'react-router-dom'
import { useAppState } from '../../state/AppState'
import { cn } from '../../lib/util'
import { competitionLabel } from '../../lib/competition.mjs'
import { Brand, CompetitionSelect, MORE_NAV, NavIcon, PRIMARY_NAV, Settings } from './Navigation'
import { EditorKeyDialog } from '../shared/EditorKeyDialog'

function ScrollPosition() {
  const location = useLocation()
  const navigation = useNavigationType()
  const { competition } = useAppState()
  const positions = useRef(new Map<string, number>())
  const key = `${competition}:${location.key}`
  useLayoutEffect(() => {
    const target = navigation === 'POP' ? positions.current.get(key) ?? 0 : 0
    const restore = () => window.scrollTo({ top: target, behavior: 'instant' })
    restore()
    // Lazy routes can initially be shorter than the stored position.
    const observer = new ResizeObserver(restore)
    if (target) observer.observe(document.querySelector('main')!)
    const remember = () => {
      if (document.documentElement.scrollHeight >= target + window.innerHeight) {
        observer.disconnect()
        positions.current.set(key, window.scrollY)
      }
    }
    window.addEventListener('scroll', remember, { passive: true })
    return () => { observer.disconnect(); window.removeEventListener('scroll', remember) }
  }, [key, navigation])
  return null
}
type Panel = 'analyses' | 'settings' | 'more'

export function AppShell() {
  const { competition, competitions } = useAppState()
  const location = useLocation()
  const [panel, setPanel] = useState<Panel | null>(null)
  const triggerRef = useRef<HTMLButtonElement | null>(null)
  const menuRef = useRef<HTMLElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const visibleMoreNav = competition === 'epl2026' ? MORE_NAV.filter(item => item.to !== '/simulator') : MORE_NAV
  const isAnalysis = visibleMoreNav.some(item => item.to === location.pathname)
  const closePanel = () => setPanel(null)
  const openPanel = (next: Panel, trigger: HTMLButtonElement) => {
    triggerRef.current = trigger
    setPanel(next)
  }
  const panelTitle = panel === 'analyses' ? 'Analysen' : panel === 'more' ? 'Analysen und Einstellungen' : 'Einstellungen'

  useEffect(() => { document.title = `Football Forecast Lab | ${competitionLabel(competition, competitions)}` }, [competition, competitions])
  useEffect(() => { setPanel(null) }, [location.key])
  useEffect(() => {
    const breakpoint = window.matchMedia('(min-width: 1024px)')
    const close = () => setPanel(null)
    breakpoint.addEventListener('change', close)
    return () => breakpoint.removeEventListener('change', close)
  }, [])
  useEffect(() => {
    if (!panel) return
    const content = contentRef.current!
    const trigger = triggerRef.current
    content.inert = true
    const originalOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    menuRef.current?.focus()
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); setPanel(null) }
      if (event.key !== 'Tab') return
      const controls = [...menuRef.current!.querySelectorAll<HTMLElement>('a,button,select,input,summary')]
        .filter(el => !el.matches(':disabled') && el.getClientRects().length > 0)
      const first = controls[0], last = controls.at(-1)
      if (event.shiftKey && (document.activeElement === first || document.activeElement === menuRef.current)) { event.preventDefault(); last?.focus() }
      else if (!event.shiftKey && (document.activeElement === last || document.activeElement === menuRef.current)) { event.preventDefault(); first?.focus() }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      content.inert = false
      document.body.style.overflow = originalOverflow
      document.removeEventListener('keydown', handleKeyDown)
      trigger?.focus({ preventScroll: true })
    }
  }, [panel])

  return <>
    <EditorKeyDialog />
    <ScrollPosition />
    <div id="app-shell-content" ref={contentRef} className="min-h-dvh">
      <a href="#main-content" className="skip-link" onClick={event => {
        event.preventDefault()
        const main = document.getElementById('main-content')
        main?.focus({ preventScroll: true })
        main?.scrollIntoView({ block: 'start' })
      }}>Zum Inhalt</a>
      <header className="shell-header">
        <div className="shell-masthead mx-auto max-w-6xl">
          <Brand />
          <div className="shell-tools">
            <CompetitionSelect />
            <button type="button" aria-haspopup="dialog" aria-expanded={panel === 'settings'} aria-controls="shell-menu" onClick={event => openPanel('settings', event.currentTarget)} className="shell-settings hidden lg:inline-flex">Einstellungen</button>
          </div>
        </div>
        <nav aria-label="Hauptnavigation" className="shell-navigation mx-auto hidden max-w-6xl lg:flex">
          {PRIMARY_NAV.map(({ to, label }) => <NavLink key={to} to={to} end={to === '/'} className="shell-nav-link">{label}</NavLink>)}
          <button type="button" aria-haspopup="dialog" aria-expanded={panel === 'analyses'} aria-controls="shell-menu" data-active={isAnalysis} onClick={event => openPanel('analyses', event.currentTarget)} className="shell-nav-link">Analysen <span aria-hidden="true">⌄</span></button>
          <span className="shell-edition">Fußball. Daten. Dein Tipp.</span>
        </nav>
      </header>
      <main id="main-content" tabIndex={-1} className="min-w-0 px-5 pb-28 pt-5 sm:px-8 lg:px-10 lg:pb-10 lg:pt-7"><div className="mx-auto max-w-6xl"><Outlet /></div></main>
      <nav aria-label="Hauptnavigation" className="mobile-navigation fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 border-t border-line bg-surface px-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] pt-2 lg:hidden">
        {PRIMARY_NAV.map(({ to, label, icon }) => <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => cn('mobile-nav-link', isActive && 'active')}><NavIcon name={icon} /><span>{label}</span></NavLink>)}
        <button type="button" aria-haspopup="dialog" aria-expanded={panel === 'more'} aria-controls="shell-menu" data-active={isAnalysis} onClick={event => openPanel('more', event.currentTarget)} className={cn('mobile-nav-link', isAnalysis && 'active')}><NavIcon name="more" /><span>Mehr</span></button>
      </nav>
    </div>
    <div hidden={!panel} className="shell-overlay" onClick={closePanel}>
      <section id="shell-menu" role="dialog" aria-modal="true" aria-label={panelTitle} tabIndex={-1} ref={menuRef} onClick={event => event.stopPropagation()} className="shell-menu">
        <div className="shell-menu-heading"><h2>{panelTitle}</h2><button type="button" onClick={closePanel} aria-label="Menü schliessen" className="min-h-11 px-3 text-sm text-fg-2 hover:bg-surface-2">Schliessen ×</button></div>
        <nav hidden={panel === 'settings'} aria-label="Analysen" className="shell-analysis-links">
          {visibleMoreNav.map(({ to, label, description, icon }) => <NavLink key={to} to={to} onClick={closePanel} className="shell-analysis-link"><NavIcon name={icon} /><span><span className="block text-sm font-semibold">{label}</span><span className="mt-1 block text-xs text-fg-2">{description}</span></span></NavLink>)}
        </nav>
        <div hidden={panel === 'analyses'} className="shell-menu-settings"><CompetitionSelect /><Settings /></div>
        <p className="mt-5 border-t border-line pt-4 text-xs text-fg-3">Football Forecast Lab · Von Sajanth Chandrakumar</p>
      </section>
    </div>
  </>
}
