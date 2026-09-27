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
    <header className="mb-7">
      <div className="kicker mb-1.5 flex items-center gap-2">
        <span className="h-px w-6 bg-emerald-a/60" />
        {competitionLabel(competition, competitions)}
      </div>
      <h1 className="text-glow font-display text-5xl font-black uppercase tracking-wide">{title}</h1>
      {subtitle && <p className="mt-1.5 text-sm text-fg-2">{subtitle}</p>}
    </header>
  )
}
