import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigationType } from 'react-router-dom'
import { useAppState } from '../../state/AppState'
import { cn } from '../../lib/util'
import { competitionLabel } from '../../lib/competition.mjs'
import { Brand, CompetitionSelect, MORE_NAV, NavIcon, PRIMARY_NAV, Settings, Sidebar } from './Sidebar'

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
export function AppShell() {
  const { competition, competitions } = useAppState()
  const location = useLocation()
  const [moreOpen, setMoreOpen] = useState(false)
  const moreButtonRef = useRef<HTMLButtonElement>(null)
  const moreMenuRef = useRef<HTMLElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const isAnalysis = MORE_NAV.some(item => item.to === location.pathname)
  const pageLabel = [...PRIMARY_NAV, ...MORE_NAV].find(item => item.to === location.pathname)?.label ?? 'Spielanalyse'
  const closeMore = () => setMoreOpen(false)

  useEffect(() => { document.title = `Football Forecast Lab | ${competitionLabel(competition, competitions)}` }, [competition, competitions])
  useEffect(() => {
    if (!moreOpen) return
    const content = contentRef.current!
    const moreButton = moreButtonRef.current
    content.inert = true
    const originalOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    moreMenuRef.current?.focus()
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); setMoreOpen(false) }
      if (event.key !== 'Tab') return
      const controls = [...moreMenuRef.current!.querySelectorAll<HTMLElement>('a,button,select')].filter(el => !el.hasAttribute('disabled'))
      const first = controls[0], last = controls.at(-1)
      if (event.shiftKey && (document.activeElement === first || document.activeElement === moreMenuRef.current)) { event.preventDefault(); last?.focus() }
      else if (!event.shiftKey && (document.activeElement === last || document.activeElement === moreMenuRef.current)) { event.preventDefault(); first?.focus() }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      content.inert = false
      document.body.style.overflow = originalOverflow
      document.removeEventListener('keydown', handleKeyDown)
      moreButton?.focus()
    }
  }, [moreOpen])

  return <>
    <ScrollPosition />
    <div ref={contentRef} className="min-h-dvh lg:flex">
      <Sidebar />
      <div className="min-w-0 flex-1">
        <header className="shell-bar flex items-center justify-between gap-3 px-5 sm:px-8 lg:px-10">
          <span className="lg:hidden"><Brand /></span>
          <div className="hidden items-center gap-3 lg:flex"><span className="shell-bar-label">Football</span><span className="text-xs text-fg-3">/</span><span className="text-xs font-semibold text-fg">{pageLabel}</span></div>
          <span className="shell-bar-context rounded border border-line px-2.5 py-1.5">{competitionLabel(competition, competitions)}</span>
        </header>
        <main className="min-w-0 px-5 pb-28 pt-7 sm:px-8 lg:px-10 lg:pb-10 lg:pt-10"><div className="mx-auto max-w-6xl"><Outlet /></div></main>
      </div>
      <nav aria-label="Hauptnavigation" className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 border-t border-line bg-surface px-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] pt-2 lg:hidden">
        {PRIMARY_NAV.map(({to,label,icon})=><NavLink key={to} to={to} end={to === '/'} onClick={closeMore} className={({isActive})=>cn('flex min-h-12 flex-col items-center justify-center gap-1.5 rounded text-[9px] font-semibold',isActive?'bg-emerald-dim text-emerald-a':'text-fg-2')}><NavIcon name={icon} />{label}</NavLink>)}
        <button type="button" ref={moreButtonRef} aria-expanded={moreOpen} aria-controls="mobile-more-menu" onClick={()=>setMoreOpen(true)} className={cn('flex min-h-12 flex-col items-center justify-center gap-1.5 rounded text-[9px] font-semibold',isAnalysis?'bg-emerald-dim text-emerald-a':'text-fg-2')}><NavIcon name="more" />Mehr</button>
      </nav>
    </div>
    {moreOpen && <div className="fixed inset-0 z-50 flex items-end bg-black/40 lg:items-center lg:justify-center" onClick={closeMore}>
      <section id="mobile-more-menu" role="dialog" aria-modal="true" aria-label="Analysen und Einstellungen" tabIndex={-1} ref={moreMenuRef} onClick={e=>e.stopPropagation()} className="max-h-[90dvh] w-full overflow-y-auto rounded-t-2xl bg-surface p-5 pb-[max(1.5rem,env(safe-area-inset-bottom))] outline-none lg:max-w-md lg:rounded-2xl">
        <div className="mb-4 flex items-center justify-between"><h2 className="text-lg font-semibold">Analysen & Einstellungen</h2><button type="button" onClick={closeMore} aria-label="Menü schliessen" className="min-h-11 rounded-lg px-3 text-sm text-fg-2 hover:bg-surface-2">Schliessen ×</button></div>
        <nav aria-label="Analysen" className="mb-5 grid gap-1">{MORE_NAV.map(({to,label,description})=><NavLink key={to} to={to} onClick={closeMore} className={({isActive})=>cn('rounded-lg px-3 py-3',isActive?'bg-emerald-dim':'hover:bg-surface-2')}><span className="block text-sm font-semibold text-fg">{label}</span><span className="mt-1 block text-xs text-fg-3">{description}</span></NavLink>)}</nav>
        <div className="space-y-4 border-t border-line pt-4"><CompetitionSelect /><Settings /></div>
      </section>
    </div>}
  </>
}
