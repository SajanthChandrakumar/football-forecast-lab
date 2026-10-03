import { useEffect, useMemo, useState } from 'react'
import { useArchive, useMatches } from '../../hooks/queries'
import { useAppState } from '../../state/AppState'
import type { Match } from '../../lib/types'
import { kickoffTime, shortDate } from '../../lib/format'
import { PageTransition, PageHeader } from '../../components/shared/PageTransition'
import { FixtureListSkeleton } from '../../components/shared/Skeleton'
import { FixtureRow } from './FixtureRow'
import { QueryState } from '../../components/shared/QueryState'
import { fixtureStatus, preferredFixtureTab } from '../../lib/fixture-status.mjs'
import { groupFixturesByRound } from '../../lib/fixture-rounds.mjs'
import { openUnsubmittedTips } from '../../lib/shared-tips.mjs'

type Tab = 'upcoming' | 'pending' | 'played' | 'unscheduled' | 'tips'
const EMPTY_MATCHES: Match[] = []

export function DashboardView() {
  const { competition } = useAppState()
  const { data: matches, availability: matchData, isLoading, error, refetch } = useMatches()
  const archiveQuery = useArchive()
  const fixtureMatches = matches ?? EMPTY_MATCHES
  const [selection, setSelection] = useState<{ competition: string; tab: Tab } | null>(() => {
    try { return JSON.parse(sessionStorage.getItem('fixture-tab') ?? 'null') } catch { return null }
  })
  const tab = selection?.competition === competition ? selection.tab : null
  const [search, setSearch] = useState(() => { try { return sessionStorage.getItem(`fixture-search:${competition}`) ?? '' } catch { return '' } })
  useEffect(() => { try { setSearch(sessionStorage.getItem(`fixture-search:${competition}`) ?? '') } catch { setSearch('') } }, [competition])
  const [openRounds, setOpenRounds] = useState<Record<string, boolean>>(() => {
    try { return JSON.parse(sessionStorage.getItem('fixture-open-rounds') ?? '{}') } catch { return {} }
  })
  const [now, setNow] = useState(() => Date.now())
  const [focusTipId, setFocusTipId] = useState<string | null>(null)
  const [tipSaveNotice, setTipSaveNotice] = useState('')

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
  const openTips = useMemo(
    () => archiveQuery.error ? [] : openUnsubmittedTips(upcoming, archiveQuery.data, now),
    [archiveQuery.error, archiveQuery.data, upcoming, now],
  )

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
        : activeTab === 'tips'
          ? openTips
          : played

  const activeIds = new Set(activeMatches.map((match) => match.id))
  const allRounds = useMemo(() => groupFixturesByRound(fixtureMatches), [fixtureMatches])
  const focusNextTip = (matchId: string) => {
    const round = allRounds.find((item) => item.matches.some((match) => match.id === matchId))
    if (round) {
      const key = `${competition}:tips:${round.key}`
      setOpenRounds((previous) => {
        if (previous[key]) return previous
        const next = { ...previous, [key]: true }
        try { sessionStorage.setItem('fixture-open-rounds', JSON.stringify(next)) } catch { /* The round stays open in memory. */ }
        return next
      })
    }
    setFocusTipId(matchId)
  }
  const nextRound = allRounds.find(round => round.matches.some(match => fixtureStatus(match, now) === 'upcoming'))
  const nextRoundMatches = nextRound?.matches.filter(match => fixtureStatus(match, now) === 'upcoming') ?? []
  const visibleRounds = allRounds
    .map((round) => {
      const matches = round.matches.filter((match) => activeIds.has(match.id) && `${match.home_team} ${match.away_team} ${match.home_disp ?? ''} ${match.away_disp ?? ''}`.toLocaleLowerCase().includes(search.toLocaleLowerCase().trim()))
      const times = matches.map((match) => Date.parse(match.raw_match?.commence_time ?? '')).filter(Number.isFinite)
      return { ...round, matches, firstKickoff: Math.min(...times), lastKickoff: Math.max(...times) }
    })
    .filter((round) => round.matches.length > 0)
  if (activeTab !== 'upcoming' && activeTab !== 'tips') visibleRounds.reverse()
  const visibleTips = activeTab === 'tips' ? visibleRounds.flatMap((round) => round.matches) : []
  const nextTipById = new Map(visibleTips.slice(0, -1).map((match, index) => [match.id, visibleTips[index + 1].id]))

  const isUnavailable = matchData?.status === 'unavailable' || matchData?.status === 'failed'
  const observedAt = matchData?.observed_at
    ? `${shortDate(matchData.observed_at)} · ${kickoffTime(matchData.observed_at)}`
    : null
  const tabs: { key: Tab; label: string; count: number }[] = [
    { key: 'upcoming', label: 'Demnächst', count: upcoming.length },
    { key: 'played', label: 'Ergebnisse', count: played.length },
    { key: 'tips', label: 'Offene gemeinsame Tipps', count: openTips.length },
    ...(pending.length ? [{ key: 'pending' as const, label: 'Ergebnis ausstehend', count: pending.length }] : []),
    ...(unscheduled.length ? [{ key: 'unscheduled' as const, label: 'Anstoß offen', count: unscheduled.length }] : []),
  ]

  return (
    <PageTransition>
      <PageHeader title="Spiele & Tipps." subtitle="Der Spielplan. Die Modelltipps. Deine nächste Entscheidung.">
        {!isLoading && fixtureMatches.length > 0 && <aside className="matchday-brief" aria-label={nextRound ? 'Nächste Spielwoche' : 'Wettbewerbsarchiv'}>
          <p className="brief-label">{nextRound ? 'Als Nächstes' : 'Im Rückblick'}</p>
          <div className="flex items-end justify-between gap-5"><h2 className="brief-heading">{nextRound?.label ?? 'Abgeschlossene Spiele'}</h2><div className="text-right"><p className="brief-count">{nextRound ? nextRoundMatches.length : played.length}</p><p className="mt-1 text-[9px] text-[#c2cebe]">Spiele</p></div></div>
          <p className="brief-date">{nextRound && Number.isFinite(nextRound.firstKickoff)
            ? `${shortDate(new Date(nextRound.firstKickoff).toISOString())}${nextRound.firstKickoff !== nextRound.lastKickoff ? ` – ${shortDate(new Date(nextRound.lastKickoff).toISOString())}` : ''}`
            : 'Gespeicherte Ergebnisse und Modellauswertungen'}</p>
        </aside>}
      </PageHeader>

      {/* Tab switcher — keeps past results out of the way */}
      <div className="fixture-toolbar">
      <div className="fixture-tabs">
        {tabs.map(({ key, label, count }) => (
          <button
            key={key}
            onClick={() => { setSelection({ competition, tab: key }); try { sessionStorage.setItem('fixture-tab', JSON.stringify({competition,tab:key})) } catch { /* Keep the in-memory selection. */ } }}
            aria-pressed={activeTab === key}
            className="fixture-tab"
          >
            {label}<span className="fixture-tab-count">{count}</span>
          </button>
        ))}
      </div>

      {fixtureMatches.length > 0 && <label className="fixture-search"><span className="sr-only">Team suchen</span><svg aria-hidden="true" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-3.5 w-3.5 shrink-0"><circle cx="8.5" cy="8.5" r="5" /><path d="m12 12 4 4" /></svg>
        <input type="search" value={search} onChange={e=>{ setSearch(e.target.value); try { sessionStorage.setItem(`fixture-search:${competition}`,e.target.value) } catch { /* Search remains available without storage. */ } }} placeholder="Team suchen" />
      </label>}
      </div>
      {isLoading && <FixtureListSkeleton days={2} rowsPerDay={4} />}
      {error && <QueryState title="Spieldaten konnten nicht geladen werden" message="Bitte versuche es erneut. Bereits gespeicherte Daten können vorübergehend veraltet sein." onRetry={()=>void refetch()} />}
      {activeTab === 'tips' && archiveQuery.isLoading && <p role="status" className="rounded-lg border border-line bg-surface px-4 py-3 text-sm text-fg-2">Gespeicherte gemeinsame Tipps werden geladen.</p>}
      {activeTab === 'tips' && archiveQuery.error && <QueryState title="Tippstatus nicht verfügbar" message="Die gespeicherten gemeinsamen Tipps konnten nicht geladen werden. Lade sie erneut, bevor du einen Tipp abgibst." onRetry={() => { void archiveQuery.refetch() }} />}
      {activeTab === 'tips' && tipSaveNotice && <p role="status" className="rounded-lg border border-emerald-a/30 bg-emerald-dim px-4 py-3 text-sm text-fg">{tipSaveNotice}</p>}
      {activeTab === 'tips' && !archiveQuery.isLoading && !archiveQuery.error && openTips.length === 0 && <p className="rounded-lg border border-line bg-surface px-4 py-5 text-sm text-fg-2">Aktuell gibt es keine archivierten Spiele mit offenem, noch nicht abgegebenem gemeinsamen Tipp.</p>}
      {activeTab === 'tips' && openTips.length > 0 && <p className="rounded-lg border border-line bg-surface px-4 py-3 text-sm leading-relaxed text-fg-2">Diese Ergebnistipps werden gemeinsam und zentral pro Spiel gespeichert. Die Eingabe schließt fünf Minuten vor Anpfiff.</p>}
      {!isLoading && !error && fixtureMatches.length === 0 && isUnavailable && (
        <div role="status" className="rounded-2xl border border-amber-a/30 bg-amber-a/5 p-5">
          <h2 className="text-base font-bold text-fg">Spieldaten gerade nicht verfügbar</h2>
          <p className="mt-1 text-sm text-fg-2">Es konnten keine aktuellen Spiele geladen werden.</p><button type="button" onClick={()=>void refetch()} className="mt-3 min-h-11 rounded-lg border border-line-2 px-4 text-sm font-semibold text-fg">Erneut versuchen</button>
          <p className="mt-2 text-xs text-fg-3">
            {matchData?.source ? `Quelle: ${matchData.source}` : 'Quelle nicht verfügbar'}
            {observedAt ? ` · Geprüft: ${observedAt}` : ''}
          </p>
        </div>
      )}
      {!isLoading && !error && fixtureMatches.length === 0 && !isUnavailable && (
        <p className="text-fg-2">Für diesen Wettbewerb sind aktuell keine Spiele verfügbar.</p>
      )}
      {!isLoading && activeTab !== 'tips' && fixtureMatches.length > 0 && visibleRounds.length === 0 && <p className="text-fg-2">Keine Spiele für diese Auswahl. Ändere die Kategorie oder den Suchbegriff.</p>}

      <div key={activeTab} className="space-y-3">
        {visibleRounds.map((round, index) => (
          <details key={`${competition}:${activeTab}:${round.key}`} open={openRounds[`${competition}:${activeTab}:${round.key}`] ?? index === 0} onToggle={e => {
            const key = `${competition}:${activeTab}:${round.key}`
            const open = e.currentTarget.open
            setOpenRounds(prev => {
              if (prev[key] === open) return prev
              const next = { ...prev, [key]: open }
              try { sessionStorage.setItem('fixture-open-rounds', JSON.stringify(next)) } catch { /* Disclosure state remains in memory. */ }
              return next
            })
          }} className="fixture-round">
            <summary className="round-summary">
              <span className="min-w-0">
                <span className="round-title">{round.label}</span>
                {Number.isFinite(round.firstKickoff) && (
                  <span className="round-date block">
                    {shortDate(new Date(round.firstKickoff).toISOString())}
                    {round.firstKickoff !== round.lastKickoff && ` – ${shortDate(new Date(round.lastKickoff).toISOString())}`}
                  </span>
                )}
              </span>
              <span className="round-count shrink-0">
                {round.matches.length} {round.matches.length === 1 ? 'Spiel' : 'Spiele'} <svg aria-hidden="true" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" className="round-chevron"><path d="m5 8 5 5 5-5" /></svg>
              </span>
            </summary>
            <div className="round-fixtures">
              <div className="fixture-column-labels" aria-hidden="true"><span>Anpfiff</span><span>Begegnung</span><span>Datenbasis</span><span>Modelltipp</span><span /></div>
              {(activeTab === 'upcoming' || activeTab === 'tips' ? round.matches : [...round.matches].reverse()).map((match) => {
                const nextMatchId = nextTipById.get(match.id)
                return <FixtureRow
                  key={`${competition}:${match.id}`}
                  match={match}
                  pendingResult={activeTab === 'pending'}
                  now={now}
                  compact
                  sharedTipMode={activeTab === 'tips'}
                  competition={competition}
                  savedTip={archiveQuery.data?.[match.id]?.prediction.user_tip}
                  autoFocusTip={focusTipId === match.id}
                  onTipAutoFocus={() => setFocusTipId((current) => current === match.id ? null : current)}
                  onSaveAndNext={nextMatchId ? () => focusNextTip(nextMatchId) : undefined}
                  onSaveStart={() => setTipSaveNotice('')}
                  onTipSaved={(tip) => setTipSaveNotice(`Gemeinsamer Tipp ${tip} für ${match.home_team} gegen ${match.away_team} gespeichert.`)}
                />
              })}
            </div>
          </details>
        ))}
      </div>
    </PageTransition>
  )
}
