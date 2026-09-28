import { motion } from 'framer-motion'
import type { ReactNode } from 'react'
import { competitionLabel } from '../../lib/competition.mjs'
import { useAppState } from '../../state/AppState'

/** Standard page entrance: 200ms fade-rise. Children can add their own stagger. */
export function PageTransition({ children }: { children: ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
    >
      {children}
    </motion.div>
  )
}

export const staggerContainer = {
  animate: { transition: { staggerChildren: 0.04 } },
}

export const staggerItem = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.25, ease: 'easeOut' as const } },
}

export function PageHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  const { competition, competitions } = useAppState()
  return (
    <header className="relative mb-7 overflow-hidden rounded-[1.75rem] bg-[#193b2b] px-5 py-7 text-left shadow-[0_18px_35px_-25px_rgba(22,48,33,0.8)] sm:px-8 sm:py-9">
      <span className="absolute inset-x-0 top-0 h-1 bg-[#c9ad78]" aria-hidden="true" />
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#cbdccf]">{competitionLabel(competition, competitions)}</p>
      <h1 className="mt-3 font-display text-4xl font-bold leading-none text-[#f8f7f2] sm:text-5xl">{title}</h1>
      {subtitle && <p className="mt-3 max-w-2xl text-sm leading-relaxed text-[#d5e3d7]">{subtitle}</p>}
    </header>
  )
}
