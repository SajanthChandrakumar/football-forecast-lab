import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { useMatches } from '../../hooks/queries'
import { useAppState } from '../../state/AppState'
import type { Match } from '../../lib/types'
import { kickoffTime, shortDate } from '../../lib/format'
import { cn } from '../../lib/util'
import { PageTransition, PageHeader } from '../../components/shared/PageTransition'
import { FixtureListSkeleton } from '../../components/shared/Skeleton'
import { FixtureRow } from './FixtureRow'
import { MatchdayRadar } from './MatchdayRadar'
import { fixtureStatus, preferredFixtureTab } from '../../lib/fixture-status.mjs'
import { groupFixturesByRound } from '../../lib/fixture-rounds.mjs'

type Tab = 'upcoming' | 'pending' | 'played' | 'unscheduled'
const EMPTY_MATCHES: Match[] = []

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

  const activeIds = new Set(activeMatches.map((match) => match.id))
  const allRounds = useMemo(() => groupFixturesByRound(fixtureMatches), [fixtureMatches])
  const visibleRounds = allRounds
    .map((round) => {
      const matches = round.matches.filter((match) => activeIds.has(match.id))
      const times = matches.map((match) => Date.parse(match.raw_match?.commence_time ?? '')).filter(Number.isFinite)
      return { ...round, matches, firstKickoff: Math.min(...times), lastKickoff: Math.max(...times) }
    })
    .filter((round) => round.matches.length > 0)
  if (activeTab !== 'upcoming') visibleRounds.reverse()

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
      <PageHeader title="Spiele" subtitle="Wähle eine Spielwoche und finde deinen Tipp." />

      {!isLoading && !error && <MatchdayRadar matches={upcoming} />}

      {/* Tab switcher — keeps past results out of the way */}
      <div className="mb-6 flex flex-wrap gap-2">
        {tabs.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setSelection({ competition, tab: key })}
            aria-pressed={activeTab === key}
            className={cn(
              'min-h-11 rounded-lg border px-4 py-2 text-sm font-semibold transition-colors',
              activeTab === key
                ? 'border-[#193b2b] bg-[#193b2b] text-[#f8f7f2]'
                : 'border-line bg-surface text-fg-2 hover:border-emerald-a hover:text-fg',
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
      {!isLoading && fixtureMatches.length > 0 && visibleRounds.length === 0 && <p className="text-fg-2">Keine Spiele in dieser Kategorie.</p>}

      <motion.div key={activeTab} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }} className="space-y-4">
        {visibleRounds.map((round) => (
          <details key={`${competition}:${activeTab}:${round.key}`} name={`fixture-rounds-${competition}-${activeTab}`} className="group overflow-hidden rounded-[1.5rem] border border-line bg-surface shadow-[0_18px_35px_-32px_rgba(22,48,33,0.55)]">
            <summary className="flex min-h-20 cursor-pointer list-none items-center justify-between gap-4 px-5 py-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-a sm:px-6 [&::-webkit-details-marker]:hidden">
              <span className="min-w-0">
                <span className="block font-display text-2xl font-bold text-fg">{round.label}</span>
                {Number.isFinite(round.firstKickoff) && (
                  <span className="mt-1 block text-sm text-fg-2">
                    {shortDate(new Date(round.firstKickoff).toISOString())}
                    {round.firstKickoff !== round.lastKickoff && ` – ${shortDate(new Date(round.lastKickoff).toISOString())}`}
                  </span>
                )}
              </span>
              <span className="flex shrink-0 items-center gap-3 text-sm font-semibold text-fg-2">
                {round.matches.length} Spiele <span aria-hidden="true" className="flex h-8 w-8 items-center justify-center rounded-full bg-[#193b2b] text-lg text-[#f8f7f2] transition-transform group-open:rotate-180">⌄</span>
              </span>
            </summary>
            <div className="grid gap-2 border-t border-line bg-bg/35 p-2 sm:grid-cols-2 sm:p-3">
              {(activeTab === 'upcoming' ? round.matches : [...round.matches].reverse()).map((match) => (
                <FixtureRow key={match.id} match={match} pendingResult={activeTab === 'pending'} now={now} compact />
              ))}
            </div>
          </details>
        ))}
      </motion.div>
    </PageTransition>
  )
}
