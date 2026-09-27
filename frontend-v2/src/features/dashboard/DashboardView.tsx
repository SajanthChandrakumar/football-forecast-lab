import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { useMatches } from '../../hooks/queries'
import { useAppState } from '../../state/AppState'
import type { Match } from '../../lib/types'
import { dayHeading, dayKey, kickoffTime, shortDate } from '../../lib/format'
import { cn } from '../../lib/util'
import { PageTransition, PageHeader } from '../../components/shared/PageTransition'
import { FixtureListSkeleton } from '../../components/shared/Skeleton'
import { FixtureRow } from './FixtureRow'
import { fixtureStatus, preferredFixtureTab } from '../../lib/fixture-status.mjs'

type Tab = 'upcoming' | 'pending' | 'played' | 'unscheduled'
const EMPTY_MATCHES: Match[] = []

function groupByDay(matches: Match[], newestFirst = false): [string, Match[]][] {
  const groups = new Map<string, Match[]>()
  const sorted = [...matches].sort((a, b) => {
    const cmp = String(a.raw_match?.commence_time ?? '').localeCompare(String(b.raw_match?.commence_time ?? ''))
    return newestFirst ? -cmp : cmp
  })
  for (const m of sorted) {
    const ct = m.raw_match?.commence_time
    const key = ct && Number.isFinite(Date.parse(ct)) ? dayKey(ct) : 'unscheduled'
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(m)
  }
  return [...groups.entries()]
}

export function DashboardView() {
  const { competition } = useAppState()
  const { data: matches, availability: matchData, isLoading, error } = useMatches()
  const fixtureMatches = matches ?? EMPTY_MATCHES
  const [selection, setSelection] = useState<{ competition: string; tab: Tab } | null>(null)
  const tab = selection?.competition === competition ? selection.tab : null
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const clock = window.setInterval(() => setNow(Date.now()), 15_000)
    return () => window.clearInterval(clock)
  }, [])

  const { upcoming, pending, played, unscheduled } = useMemo(() => {
    const upcoming: Match[] = []
    const pending: Match[] = []
    const played: Match[] = []
    const unscheduled: Match[] = []
    for (const m of fixtureMatches) {
      const status = fixtureStatus(m, now)
      if (status === 'played') played.push(m)
      else if (status === 'pending') pending.push(m)
      else if (status === 'unscheduled') unscheduled.push(m)
      else upcoming.push(m)
    }
    return { upcoming, pending, played, unscheduled }
  }, [fixtureMatches, now])

  const validTab = (tab === 'pending' && pending.length === 0) || (tab === 'unscheduled' && unscheduled.length === 0) ? null : tab
  const activeTab = validTab ?? preferredFixtureTab({
    upcoming: upcoming.length,
    pending: pending.length,
    played: played.length,
    unscheduled: unscheduled.length,
  })
  const activeMatches = activeTab === 'upcoming'
    ? upcoming
    : activeTab === 'pending'
      ? pending
      : activeTab === 'unscheduled'
        ? unscheduled
        : played

  const days = useMemo(
    () => groupByDay(activeMatches, activeTab !== 'upcoming'),
    [activeTab, activeMatches],
  )

  const isUnavailable = matchData?.status === 'unavailable' || matchData?.status === 'failed'
  const observedAt = matchData?.observed_at
    ? `${shortDate(matchData.observed_at)} · ${kickoffTime(matchData.observed_at)}`
    : null
  const tabs: { key: Tab; label: string }[] = [
    { key: 'upcoming', label: `Kommende Spiele (${upcoming.length})` },
    { key: 'played', label: `Gespielt (${played.length})` },
    ...(pending.length ? [{ key: 'pending' as const, label: `Ergebnis ausstehend (${pending.length})` }] : []),
    ...(unscheduled.length ? [{ key: 'unscheduled' as const, label: `Anstoß offen (${unscheduled.length})` }] : []),
  ]

  return (
    <PageTransition>
      <div className="text-center">
        <PageHeader title="Spiele" subtitle="Wähle ein Spiel für Tipp und Analyse" />
      </div>

      {/* Tab switcher — keeps past results out of the way */}
      <div className="mb-6 flex flex-wrap gap-1.5">
        {tabs.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setSelection({ competition, tab: key })}
            aria-pressed={activeTab === key}
            className={cn(
              'min-h-11 rounded-xl border px-4 py-2 text-sm font-bold transition',
              activeTab === key
                ? 'border-emerald-a/50 bg-emerald-dim text-emerald-a'
                : 'border-line bg-surface text-fg-2 hover:bg-surface-2',
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {isLoading && <FixtureListSkeleton days={2} rowsPerDay={4} />}
      {error && <p role="alert" className="rounded-xl border border-red-a/30 bg-red-a/5 p-4 text-sm text-red-a">Spieldaten konnten nicht geladen werden. Bitte später erneut versuchen.</p>}
      {!isLoading && !error && fixtureMatches.length === 0 && isUnavailable && (
        <div role="status" className="rounded-2xl border border-amber-a/30 bg-amber-a/5 p-5">
          <h2 className="text-base font-bold text-fg">Spieldaten gerade nicht verfügbar</h2>
          <p className="mt-1 text-sm text-fg-2">Es konnten keine aktuellen Spiele geladen werden. Bitte später erneut versuchen.</p>
          <p className="mt-2 text-xs text-fg-3">
            {matchData?.source ? `Quelle: ${matchData.source}` : 'Quelle nicht verfügbar'}
            {observedAt ? ` · Geprüft: ${observedAt}` : ''}
          </p>
        </div>
      )}
      {!isLoading && !error && fixtureMatches.length === 0 && !isUnavailable && (
        <p className="text-fg-2">Für diesen Wettbewerb sind aktuell keine Spiele verfügbar.</p>
      )}
      {!isLoading && fixtureMatches.length > 0 && days.length === 0 && <p className="text-fg-2">Keine Spiele in dieser Kategorie.</p>}

      {/* No per-row stagger here — with 80+ rows it takes seconds to settle. */}
      <motion.div key={activeTab} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }} className="space-y-4">
        {days.map(([key, dayMatches]) => (
          <section key={key}>
            <h3 className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.15em] text-fg-3">
              <span className="h-px w-4 bg-line-2" />
              {key === 'unscheduled' ? 'Anstoß noch nicht festgelegt' : dayHeading(String(dayMatches[0].raw_match!.commence_time))}
              <span className="text-fg-3/60">· {dayMatches.length}</span>
            </h3>
            <div className="space-y-3">
              {dayMatches.map((m) => (
                <FixtureRow key={m.id} match={m} pendingResult={activeTab === 'pending'} now={now} />
              ))}
            </div>
          </section>
        ))}
      </motion.div>
    </PageTransition>
  )
}
