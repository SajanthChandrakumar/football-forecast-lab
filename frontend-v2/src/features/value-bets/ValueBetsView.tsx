import { useEffect, useMemo, useState } from 'react'
import { useMatches } from '../../hooks/queries'
import { useAppState } from '../../state/AppState'
import { PageTransition, PageHeader } from '../../components/shared/PageTransition'
import { FixtureListSkeleton } from '../../components/shared/Skeleton'
import { QueryState } from '../../components/shared/QueryState'
import { FixtureRow } from '../dashboard/FixtureRow'
import { rankUpcomingValueBets } from '../../lib/value-bets.mjs'

export function ValueBetsView() {
  const { competition } = useAppState()
  const { data: matches, availability, isLoading, error, refetch } = useMatches()
  const [now, setNow] = useState(() => Date.now())
  const [selection, setSelection] = useState({ competition, period: 'next', limit: 12 })
  const period = selection.competition === competition ? selection.period : 'next'
  const limit = selection.competition === competition ? selection.limit : 12
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 30_000); return () => window.clearInterval(timer) }, [])
  const ranked = useMemo(() => rankUpcomingValueBets(matches, now, period), [matches, now, period])
  const unavailable = ['failed', 'unavailable'].includes(availability?.status ?? '')
  return <PageTransition>
    <PageHeader title="Tipp-Chancen" subtitle="Welche Spiele versprechen die meisten Tippspielpunkte? Vergleiche die Empfehlungen im gewählten Zeitraum." />
    <div className="mb-5 flex flex-wrap gap-2">{[['next','Nächste Spielwoche'],['all','Alle kommenden Spiele']].map(([key,label])=><button key={key} type="button" aria-pressed={period === key} onClick={()=>setSelection({competition, period:key,limit:12})} className={`min-h-11 rounded-lg border px-4 text-sm font-medium ${period === key ? 'border-emerald-a bg-emerald-dim text-emerald-a' : 'border-line bg-surface text-fg-2'}`}>{label}</button>)}</div>
    <p className="mb-5 text-xs leading-relaxed text-fg-3">Erwartete Punkte sind ein Modelldurchschnitt nach den Tippspielregeln. Sie sind keine exakte Trefferchance. Buchmacherquoten und Elo-Modellwerte sind an den Spielen gekennzeichnet.</p>
    {isLoading ? <FixtureListSkeleton days={1} rowsPerDay={4} /> : error || unavailable ? <QueryState title="Spieldaten nicht verfügbar" message="Die Empfehlungen konnten nicht geladen werden. Bitte versuche es erneut." onRetry={()=>void refetch()} /> : ranked.length === 0 ? <QueryState title="Keine Empfehlungen in diesem Zeitraum" message="Es liegen noch keine kommenden Spiele mit berechnetem Tippwert vor." /> : <>
      <p className="mb-3 text-xs font-medium text-fg-3">{ranked.length} Empfehlungen · nach erwarteten Punkten sortiert</p>
      <div className="overflow-hidden rounded-lg border border-line">{ranked.slice(0,limit).map((m,i)=><FixtureRow key={m.id} match={m} now={now} compact trailing={<span className="text-xs text-fg-2">#{i+1} · <b className="font-semibold tabular-nums text-fg">{m.max_xp.toFixed(2)} erwartete Punkte</b></span>} />)}</div>
      {ranked.length > limit && <button type="button" onClick={()=>setSelection({competition,period,limit:limit+12})} className="mt-5 min-h-11 rounded-lg border border-line-2 bg-surface px-5 text-sm font-semibold text-fg">Weitere Empfehlungen anzeigen ({ranked.length-limit})</button>}
    </>}
  </PageTransition>
}
