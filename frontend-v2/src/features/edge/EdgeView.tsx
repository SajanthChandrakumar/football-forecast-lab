import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMatches } from '../../hooks/queries'
import { cn } from '../../lib/util'
import { TeamLogo } from '../../components/shared/Badges'
import { shortDate } from '../../lib/format'
import { fixtureStatus } from '../../lib/fixture-status.mjs'
import { PageTransition, PageHeader } from '../../components/shared/PageTransition'
import { CardGridSkeleton } from '../../components/shared/Skeleton'
import { QueryState } from '../../components/shared/QueryState'
import type { Match } from '../../lib/types'

type EdgeGrade = 'hit' | 'miss' | 'close'

interface GradedEdgeMatch {
  match: Match
  edgePp: number
  absEdge: number
  grade?: EdgeGrade
}

function gradeEdge(match: Match, edgePp: number): EdgeGrade | undefined {
  if (!match.actual_score) return undefined
  const parts = match.actual_score.split(':')
  if (parts.length !== 2) return undefined
  const homeGoals = Number.parseInt(parts[0], 10)
  const awayGoals = Number.parseInt(parts[1], 10)
  if (Number.isNaN(homeGoals) || Number.isNaN(awayGoals)) return undefined
  if (Math.abs(edgePp) < 2 || homeGoals === awayGoals) return 'close'
  return (edgePp > 0) === (homeGoals > awayGoals) ? 'hit' : 'miss'
}

export function EdgeView() {
  const { data: matches, availability, isLoading, error, refetch } = useMatches()
  const navigate = useNavigate()
  const [tab, setTab] = useState<'upcoming' | 'history'>('upcoming')

  const { upcoming, historical, stats } = useMemo(() => {
    const up: GradedEdgeMatch[] = []
    const hist: GradedEdgeMatch[] = []

    for (const match of matches ?? []) {
      if (match.edge_home == null || match.market_home_share == null || match.elo_home_share == null) continue
      const edgePp = match.edge_home * 100
      const status = fixtureStatus(match)
      if (status === 'upcoming') up.push({ match, edgePp, absEdge: Math.abs(edgePp) })
      else if (status === 'played') hist.push({ match, edgePp, absEdge: Math.abs(edgePp), grade: gradeEdge(match, edgePp) })
    }

    up.sort((a, b) => b.absEdge - a.absEdge)
    hist.sort((a, b) => b.absEdge - a.absEdge)
    const hits = hist.filter((item) => item.grade === 'hit').length
    const misses = hist.filter((item) => item.grade === 'miss').length
    const closes = hist.filter((item) => item.grade === 'close').length
    const decisive = hits + misses
    return {
      upcoming: up,
      historical: hist,
      stats: { hits, misses, closes, hitRate: decisive ? hits / decisive * 100 : 0 },
    }
  }, [matches])

  const activeCards = tab === 'upcoming' ? upcoming : historical
  const unavailable = availability?.status === 'unavailable'

  return (
    <PageTransition>
      <PageHeader title="Modellvergleich" subtitle="Vergleich des Heimsieg-Anteils zwischen Markt und Elo-Modell." />
      <p className="mb-5 max-w-3xl rounded-xl border border-line bg-surface px-4 py-3 text-sm leading-relaxed text-fg-2">
        Beide Werte teilen Sieg und Niederlage auf 100 % auf und lassen ein mögliches Remis heraus. Sie sind daher keine absoluten 1/X/2-Siegwahrscheinlichkeiten. „Prozentpunkte“ zeigen den Abstand zwischen den beiden Anteilen.
      </p>

      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Spiele auswählen">
          <button type="button" aria-pressed={tab === 'upcoming'} onClick={() => setTab('upcoming')} className={tabButtonClass(tab === 'upcoming')}>
            Kommende Spiele ({upcoming.length})
          </button>
          <button type="button" aria-pressed={tab === 'history'} onClick={() => setTab('history')} className={tabButtonClass(tab === 'history')}>
            Gespielte Spiele ({historical.length})
          </button>
        </div>

        {tab === 'history' && historical.length > 0 && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-fg-2">
            <span>Trefferquote bei klarer Modellkante: <b className="tabular-nums text-fg">{stats.hitRate.toFixed(0)}%</b></span>
            <span><b className="font-medium text-fg">{stats.hits}</b> Treffer · <b className="font-medium text-fg">{stats.closes}</b> knapp/Remis · <b className="font-medium text-fg">{stats.misses}</b> verfehlt</span>
          </div>
        )}
      </div>

      {isLoading && <CardGridSkeleton count={4} />}
      {!isLoading && error && <QueryState title="Spieldaten konnten nicht geladen werden" message="Der Modellvergleich konnte nicht aktualisiert werden." onRetry={() => void refetch()} />}
      {!isLoading && !error && unavailable && <QueryState title="Spieldaten derzeit nicht verfügbar" message="Für diesen Zeitraum stehen aktuell keine verwendbaren Daten zur Verfügung." onRetry={() => void refetch()} />}

      {!isLoading && !error && !unavailable && activeCards.length === 0 && (
        <div className="rounded-xl border border-line bg-surface px-5 py-8 text-center text-sm text-fg-2">
          {tab === 'upcoming' ? 'Keine kommenden Spiele mit vollständigen Markt- und Elo-Daten.' : 'Für gespielte Spiele liegen noch keine auswertbaren Vergleiche vor.'}
        </div>
      )}

      {!isLoading && !error && !unavailable && activeCards.length > 0 && <div className="grid gap-3 md:grid-cols-2">
        {activeCards.map(({ match, edgePp, grade }) => {
          const market = match.market_home_share! * 100
          const elo = match.elo_home_share! * 100
          const absEdge = Math.abs(edgePp)
          const edgeCopy = absEdge < 0.05
            ? 'Elo-Modell und Markt weisen dem Heimsieg denselben Anteil ohne Remis zu.'
            : edgePp > 0
            ? `Elo gibt dem Heimsieg-Anteil ohne Remis ${absEdge.toFixed(1)} Prozentpunkte mehr Gewicht als der Markt.`
            : `Elo gibt dem Heimsieg-Anteil ohne Remis ${absEdge.toFixed(1)} Prozentpunkte weniger Gewicht als der Markt.`
          const kickoff = match.raw_match?.commence_time

          return (
            <button key={match.id} type="button" onClick={() => navigate(`/match/${match.id}`)} className="rounded-xl border border-line bg-surface p-4 text-left transition hover:border-line-2 hover:bg-surface-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--blue)]">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1 font-semibold text-fg">
                    <span className="inline-flex items-center gap-1.5"><TeamLogo name={match.home_team} src={match.home_logo} />{match.home_team}</span>
                    <span className="text-fg-3">gegen</span>
                    <span className="inline-flex items-center gap-1.5"><TeamLogo name={match.away_team} src={match.away_logo} />{match.away_team}</span>
                  </div>
                  <div className="mt-1 text-xs text-fg-3">{kickoff ? shortDate(kickoff) : 'Anstoss offen'}</div>
                </div>
                {grade && <GradeBadge grade={grade} actualScore={match.actual_score} />}
              </div>

              <p className="mt-4 text-sm leading-relaxed text-fg-2">{edgeCopy}</p>
              <div className="mt-4 space-y-3">
                <Bar label="Markt · Heimsieg ohne Remis" value={market} color="var(--text-3)" />
                <Bar label="Elo · Heimsieg ohne Remis" value={elo} color="var(--blue)" />
              </div>
            </button>
          )
        })}
      </div>}
    </PageTransition>
  )
}

function tabButtonClass(active: boolean) {
  return cn('min-h-11 rounded-lg border px-4 py-2 text-sm font-medium transition', active ? 'border-line-2 bg-surface-2 text-fg' : 'border-line bg-surface text-fg-2 hover:bg-surface-2')
}

function GradeBadge({ grade, actualScore }: { grade: EdgeGrade; actualScore?: string | null }) {
  const label = grade === 'hit' ? 'Treffer' : grade === 'miss' ? 'Verfehlt' : 'Knapp oder Remis'
  const style = grade === 'hit' ? 'border-emerald-a/30 bg-emerald-a/5 text-emerald-a' : grade === 'miss' ? 'border-red-a/30 bg-red-a/5 text-red-a' : 'border-amber-a/30 bg-amber-a/5 text-amber-a'
  return <span className={cn('shrink-0 rounded-md border px-2 py-1 text-xs font-medium', style)}>{label}{actualScore ? ` · ${actualScore}` : ''}</span>
}

function Bar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-3 text-xs">
        <span className="text-fg-2">{label}</span><span className="shrink-0 tabular-nums text-fg">{value.toFixed(1)}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-surface-2" aria-hidden="true">
        <div className="h-full rounded-full" style={{ width: `${Math.max(0, Math.min(100, value))}%`, background: color }} />
      </div>
    </div>
  )
}
