import type { ReactNode } from 'react'

export function PageTransition({ children }: { children: ReactNode }) {
  return <div>{children}</div>
}
export const staggerContainer = { animate: { transition: { staggerChildren: 0 } } }
export const staggerItem = { initial: { opacity: 1 }, animate: { opacity: 1 } }

export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: string; children?: ReactNode }) {
  return <header className="page-header">
    <div className="min-w-0">
      <h1 className="page-title">{title}</h1>
      {subtitle && <p className="page-description">{subtitle}</p>}
    </div>
    {children}
  </header>
}
