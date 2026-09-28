import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { useMatches } from '../../hooks/queries'
import { cn } from '../../lib/util'
import { PageTransition, PageHeader } from '../../components/shared/PageTransition'
import { FixtureListSkeleton } from '../../components/shared/Skeleton'
import { RankBadge } from '../../components/shared/Badges'
import { FixtureRow } from '../dashboard/FixtureRow'
import { rankUpcomingValueBets } from '../../lib/value-bets.mjs'

export function ValueBetsView() {
  const { data: matches, isLoading } = useMatches()
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const clock = window.setInterval(() => setNow(Date.now()), 30_000)
    return () => window.clearInterval(clock)
  }, [])

  const ranked = useMemo(
    () => rankUpcomingValueBets(matches, now),
    [matches, now],
  )

  return (
    <PageTransition>
      <PageHeader title="Tipp-Chancen" subtitle="Spiele mit den höchsten erwarteten Punkten (xP)." />
      {isLoading && <FixtureListSkeleton days={1} rowsPerDay={6} />}
      {!isLoading && ranked.length === 0 && <p className="rounded-xl border border-line bg-surface p-5 text-sm text-fg-2">Aktuell gibt es keine kommenden Spiele mit berechnetem Tippwert.</p>}

      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }}
        className={cn('glass overflow-hidden !p-0', isLoading && 'hidden')}
      >
        {ranked.map((m, i) => (
          <div key={m.id} className="flex items-center gap-3 border-b border-line pl-4 last:border-b-0">
            <RankBadge rank={i + 1} />
            <div className="min-w-0 flex-1">
              <FixtureRow
                match={m}
                now={now}
                trailing={
                  <span className="text-right">
                    <span className="display-num block text-lg text-emerald-a">{m.max_xp.toFixed(2)}</span>
                    <span className="block text-[10px] uppercase tracking-wider text-fg-3">xP · {m.top_tip}</span>
                  </span>
                }
              />
            </div>
          </div>
        ))}
      </motion.div>
    </PageTransition>
  )
}
