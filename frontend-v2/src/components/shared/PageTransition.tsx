import type { ReactNode } from 'react'
import { competitionLabel } from '../../lib/competition.mjs'
import { useAppState } from '../../state/AppState'

export function PageTransition({ children }: { children: ReactNode }) {
  return <div>{children}</div>
}
export const staggerContainer = { animate: { transition: { staggerChildren: 0 } } }
export const staggerItem = { initial: { opacity: 1 }, animate: { opacity: 1 } }

export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: string; children?: ReactNode }) {
  const { competition, competitions } = useAppState()
  return <header className="page-header">
    <div className="min-w-0">
      <p className="page-kicker">{competitionLabel(competition, competitions)}</p>
      <h1 className="page-title">{title}</h1>
      {subtitle && <p className="page-description">{subtitle}</p>}
    </div>
    {children}
  </header>
}
