import { useMemo, useState } from 'react'
import { cn } from '../../lib/util'
import { shortDate } from '../../lib/format'
import { GlassCard, SectionTitle } from '../../components/shared/GlassCard'
import { PointsBadge, TeamLogo } from '../../components/shared/Badges'
import type { CompletedMatch } from './usePerformanceData'

type Filter = 'all' | 'hit' | 'miss' | 'notipped'

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'Alle Spiele' },
  { key: 'hit', label: 'Richtige Tendenz' },
  { key: 'miss', label: 'Falsche Tendenz' },
  { key: 'notipped', label: 'Ohne gemeinsamen Tipp' },
]

const PAGE_SIZE = 12

export function MatchHistory({ completed, hasReconstructed }: {
  completed: CompletedMatch[]
  hasReconstructed: boolean
}) {
  const [filter, setFilter] = useState<Filter>('all')
  const [limit, setLimit] = useState(PAGE_SIZE)

  const filtered = useMemo(() => completed.filter(({ entry, points }) => {
    const hasTip = entry.prediction?.user_tip != null
    switch (filter) {
      case 'hit': return hasTip && points >= 5
      case 'miss': return hasTip && points < 5
      case 'notipped': return !hasTip
      default: return true
    }
  }), [completed, filter])

  const visible = filtered.slice(0, limit)
  const remaining = filtered.length - visible.length

  return (
    <GlassCard className="!p-0">
      <div className="border-b border-line px-4 py-4 sm:px-5">
        <SectionTitle className="mb-3">Abgeschlossene Spiele</SectionTitle>
        <div className="flex flex-wrap gap-2" aria-label="Spiele filtern">
          {FILTERS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              aria-pressed={filter === key}
              onClick={() => { setFilter(key); setLimit(PAGE_SIZE) }}
              className={cn(
                'min-h-10 rounded-lg border px-3 py-1.5 text-xs font-semibold transition',
                filter === key
                  ? 'border-blue-a bg-blue-a/10 text-blue-a'
                  : 'border-line bg-surface text-fg-2 hover:bg-surface-2',
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {completed.length === 0 ? (
        <p className="px-5 py-6 text-sm text-fg-2">Noch keine abgeschlossenen Spiele.</p>
      ) : (
        <div className="grid gap-3 p-4 sm:grid-cols-2 sm:p-5">
          {visible.map((cm) => <MatchCard key={cm.id} cm={cm} />)}
          {visible.length === 0 && <p className="text-sm text-fg-2">Keine Spiele für diesen Filter.</p>}
        </div>
      )}

      {remaining > 0 && (
        <div className="px-5 pb-5 text-center">
          <button
            type="button"
            onClick={() => setLimit((l) => l + PAGE_SIZE)}
            className="min-h-11 rounded-lg border border-line px-4 py-2 text-sm font-semibold text-fg-2 hover:bg-surface-2"
          >
            {remaining} weitere {remaining === 1 ? 'Spiel' : 'Spiele'} anzeigen
          </button>
        </div>
      )}

      {hasReconstructed && (
        <p className="border-t border-line px-5 py-3 text-xs text-fg-3">
          Mit * markierte Modelltipps wurden nachträglich aus Elo-Ratings rekonstruiert.
        </p>
      )}
    </GlassCard>
  )
}

function MatchCard({ cm }: { cm: CompletedMatch }) {
  const { entry, points } = cm
  const userTip = entry.prediction?.user_tip ?? null
  const modelTip = entry.prediction?.top_tip ?? null
  const date = entry.metadata?.commence_time
    ? shortDate(entry.metadata.commence_time)
    : shortDate(entry.pre_match_snapshot?.timestamp_recorded ?? null)

  return (
    <article className="overflow-hidden rounded-lg border border-line bg-surface">
      <div className="flex items-center gap-3 border-b border-line px-3 py-3">
        <span className="shrink-0 text-xs font-medium text-fg-3">{date}</span>
        <span className="min-w-0 flex flex-1 items-center gap-1 truncate text-sm font-semibold text-fg">
          <TeamLogo name={entry.metadata.home_team} /><span className="truncate">{entry.metadata.home_team}</span>
          <span className="mx-1 font-normal text-fg-3">–</span>
          <TeamLogo name={entry.metadata.away_team} /><span className="truncate">{entry.metadata.away_team}</span>
        </span>
        <span className="shrink-0 rounded-md border border-line px-2 py-1 font-mono text-sm font-semibold text-fg" aria-label={`Endstand ${entry.post_match_result.actual_score ?? 'nicht verfügbar'}`}>
          {entry.post_match_result.actual_score ?? '—'}
        </span>
      </div>

      <div className="px-3 py-2">
        <HistoryTipRow
          label={`Modell${entry.prediction?.algo_reconstructed ? '*' : ''}`}
          tip={modelTip}
          points={entry.post_match_result.algo_points}
        />
        <HistoryTipRow label="Gemeinsamer Tipp" tip={userTip} points={userTip ? points : null} />
      </div>
    </article>
  )
}

function HistoryTipRow({ label, tip, points }: { label: string; tip?: string | null; points?: number | null }) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 border-b border-line py-2 last:border-b-0">
      <span className="text-xs font-medium text-fg-2">{label}</span>
      <span className="font-mono text-sm font-semibold tabular-nums text-fg">{tip ?? '—'}</span>
      <PointsBadge points={points} />
    </div>
  )
}
