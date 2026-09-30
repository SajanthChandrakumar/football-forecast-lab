import { useMemo, useState } from 'react'
import { cn } from '../../lib/util'
import { shortDate } from '../../lib/format'
import { GlassCard, SectionTitle } from '../../components/shared/GlassCard'
import { PointsBadge, TeamLogo } from '../../components/shared/Badges'
import { performanceEntryKind } from '../../lib/performance.mjs'
import { HOUSE_BOTS, type CompletedMatch } from './usePerformanceData'

type Filter = 'all' | 'hit' | 'miss' | 'notipped'

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'Alle' },
  { key: 'hit', label: '✓ Treffer' },
  { key: 'miss', label: '✗ Daneben' },
  { key: 'notipped', label: 'Kein Tipp' },
]

const PAGE_SIZE = 12

export function MatchHistory({ completed, hasLegacy, hasReconstructed }: {
  completed: CompletedMatch[]
  hasLegacy: boolean
  hasReconstructed: boolean
}) {
  const [filter, setFilter] = useState<Filter>('all')
  const [limit, setLimit] = useState(PAGE_SIZE)

  const filtered = useMemo(() => completed.filter(({ entry, points }) => {
    const hasTip = entry.prediction?.user_tip != null
    switch (filter) {
      case 'hit': return hasTip && points >= 5
      case 'miss': return hasTip && points === 0
      case 'notipped': return !hasTip
      default: return true
    }
  }), [completed, filter])

  const visible = filtered.slice(0, limit)
  const remaining = filtered.length - visible.length

  return (
    <GlassCard className="!p-0">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
        <SectionTitle>Match History</SectionTitle>
        <div className="flex gap-1.5">
          {FILTERS.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => { setFilter(key); setLimit(PAGE_SIZE) }}
              className={cn(
                'rounded-lg border px-3 py-1.5 text-xs font-semibold transition',
                filter === key
                  ? 'border-emerald-a/50 bg-emerald-dim text-emerald-a'
                  : 'border-line bg-surface text-fg-2 hover:bg-surface-2',
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 p-5 md:grid-cols-2">
        {visible.map((cm) => <MatchCard key={cm.id} cm={cm} />)}
        {visible.length === 0 && (
          <p className="text-sm text-fg-3">Keine Spiele in dieser Kategorie.</p>
        )}
      </div>

      {remaining > 0 && (
        <div className="px-5 pb-5 text-center">
          <button
            onClick={() => setLimit((l) => l + PAGE_SIZE)}
            className="rounded-xl border border-line bg-surface px-5 py-2 text-sm font-semibold text-fg-2 transition hover:border-emerald-a/40 hover:text-fg"
          >
            {remaining} weitere Spiele anzeigen ↓
          </button>
        </div>
      )}

      {(hasLegacy || hasReconstructed) && (
        <p className="border-t border-line px-5 py-3 text-[11px] italic text-fg-3">
          Altbestand ist nicht vollständig als Vorab-Tipp belegbar. Rekonstruktionen sind Elo-Näherungen ohne historische Buchmacherquoten.
        </p>
      )}
    </GlassCard>
  )
}

function MatchCard({ cm }: { cm: CompletedMatch }) {
  const { entry, points } = cm
  const userTip = entry.prediction?.user_tip ?? null
  const algoKind = performanceEntryKind(entry)
  const algoLabel = algoKind === 'verified' ? 'Algo · Vorab' : algoKind === 'reconstructed' ? 'Algo · Rekonstr.' : 'Algo · Alt'
  const hasTip = userTip != null
  const resultClass = !hasTip
    ? 'border-l-line'
    : points >= 8 ? 'border-l-emerald-a' : points >= 5 ? 'border-l-amber-a' : 'border-l-red-a'

  const date = entry.metadata?.commence_time
    ? shortDate(entry.metadata.commence_time)
    : shortDate(entry.pre_match_snapshot?.timestamp_recorded ?? null)

  return (
    <div className={cn('overflow-hidden rounded-xl border border-line border-l-[3px] bg-surface', resultClass)}>
      <div className="flex items-center gap-3 border-b border-line px-4 py-2.5">
        <span className="shrink-0 text-[11px] font-semibold text-fg-3">{date}</span>
        <span className="min-w-0 flex flex-1 items-center gap-1 truncate text-sm font-semibold text-fg">
          <TeamLogo name={entry.metadata.home_team} /><span className="truncate">{entry.metadata.home_team}</span>
          <span className="mx-1 font-normal text-fg-3">vs</span>
          <TeamLogo name={entry.metadata.away_team} /><span className="truncate">{entry.metadata.away_team}</span>
        </span>
        <span className="display-num shrink-0 rounded-lg border border-line-2 bg-surface-2 px-2.5 py-0.5 text-fg">
          {entry.post_match_result.actual_score}
        </span>
      </div>

      <div className="px-4 py-2">
        <TipRow
          label={algoLabel}
          color="var(--blue)"
          tip={entry.prediction?.top_tip}
          pts={entry.post_match_result.algo_points}
        />
        <UserTipRow cm={cm} />
        {HOUSE_BOTS.map((b) => {
          const tip = entry.prediction?.bots?.[b.key]?.tip
          if (!tip) return null
          return (
            <TipRow
              key={b.key} label={b.label} color={b.color} tip={tip}
              pts={entry.post_match_result.bot_points?.[b.key]}
            />
          )
        })}
      </div>
    </div>
  )
}

function TipRow({ label, color, tip, pts }: {
  label: string; color: string; tip?: string | null; pts?: number | null
}) {
  return (
    <div className="grid grid-cols-[72px_1fr_auto] items-center gap-2 border-b border-line py-1.5 last:border-b-0">
      <span className="text-[10px] font-bold uppercase tracking-wide" style={{ color }}>{label}</span>
      <span className="display-num text-sm text-fg">{tip ?? '–'}</span>
      <PointsBadge points={pts} />
    </div>
  )
}

function UserTipRow({ cm }: { cm: CompletedMatch }) {
  const { entry, points } = cm
  const userTip = entry.prediction?.user_tip ?? null
  const isSharedHistoricalTip = entry.prediction?.user_tip_source === 'shared_historical'

  return (
    <div className="grid grid-cols-[72px_1fr_auto] items-center gap-2 border-b border-line py-1.5 last:border-b-0">
      <span className="text-[10px] font-bold uppercase tracking-wide text-gold-a">{isSharedHistoricalTip ? 'Geteilt' : 'Du'}</span>
      <span className="display-num text-sm text-fg" title={userTip ? undefined : 'Die Tippfrist ist nach Anpfiff geschlossen.'}>
        {userTip ?? 'Tippfrist vorbei'}
      </span>
      <PointsBadge points={userTip ? points : null} />
    </div>
  )
}
