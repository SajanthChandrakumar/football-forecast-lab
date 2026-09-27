import { useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { useMatches } from '../../hooks/queries'
import type { Match } from '../../lib/types'
import { dayHeading, dayKey } from '../../lib/format'
import { cn } from '../../lib/util'
import { PageTransition, PageHeader } from '../../components/shared/PageTransition'
import { FixtureListSkeleton } from '../../components/shared/Skeleton'
import { FixtureRow } from './FixtureRow'

type Tab = 'upcoming' | 'played'

function groupByDay(matches: Match[], newestFirst = false): [string, Match[]][] {
  const groups = new Map<string, Match[]>()
  const sorted = [...matches].sort((a, b) => {
    const cmp = String(a.raw_match?.commence_time ?? '').localeCompare(String(b.raw_match?.commence_time ?? ''))
    return newestFirst ? -cmp : cmp
  })
  for (const m of sorted) {
    const ct = m.raw_match?.commence_time
    if (!ct) continue
    const key = dayKey(ct)
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(m)
  }
  return [...groups.entries()]
}

export function DashboardView() {
  const { data: matches, isLoading, error } = useMatches()
  const [tab, setTab] = useState<Tab>('upcoming')

  const { upcoming, played } = useMemo(() => {
    const upcoming: Match[] = []
    const played: Match[] = []
    for (const m of matches ?? []) {
      if (m.completed || m.actual_score) played.push(m)
      else upcoming.push(m)
    }
    return { upcoming, played }
  }, [matches])

  const days = useMemo(
    () => groupByDay(tab === 'upcoming' ? upcoming : played, tab === 'played'),
    [tab, upcoming, played],
  )

  return (
    <PageTransition>
      <div className="text-center">
        <PageHeader title="Kommende Spiele" subtitle="Wähle ein Spiel für die vollständige Analyse" />
      </div>

      {/* Tab switcher — keeps past results out of the way */}
      <div className="mb-6 flex gap-1.5">
        {([
          { key: 'upcoming', label: `Kommende Spiele (${upcoming.length})` },
          { key: 'played', label: `Gespielt (${played.length})` },
        ] as { key: Tab; label: string }[]).map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={cn(
              'min-h-11 rounded-xl border px-4 py-2 text-sm font-bold transition',
              tab === key
                ? 'border-emerald-a/50 bg-emerald-dim text-emerald-a'
                : 'border-line bg-surface text-fg-2 hover:bg-surface-2',
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {isLoading && <FixtureListSkeleton days={2} rowsPerDay={4} />}
      {error && <p className="text-red-a">Fehler: {(error as Error).message}</p>}
      {!isLoading && days.length === 0 && <p className="text-fg-2">Keine Spiele in dieser Kategorie.</p>}

      {/* No per-row stagger here — with 80+ rows it takes seconds to settle. */}
      <motion.div key={tab} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }} className="space-y-7">
        {days.map(([key, dayMatches]) => (
          <section key={key}>
            <h3 className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.15em] text-fg-3">
              <span className="h-px w-4 bg-line-2" />
              {dayHeading(String(dayMatches[0].raw_match!.commence_time))}
              <span className="text-fg-3/60">· {dayMatches.length}</span>
            </h3>
            <div className="glass overflow-hidden !p-0">
              {dayMatches.map((m) => (
                <FixtureRow key={m.id} match={m} />
              ))}
            </div>
          </section>
        ))}
      </motion.div>
    </PageTransition>
  )
}
