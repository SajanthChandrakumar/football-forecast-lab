import { computeImpliedProbs, pct } from '../../lib/util'
import type { Odds, Probabilities } from '../../lib/types'

/** 3-segment implied-probability bar (home / draw / away). */
export function ProbBar({ odds, probabilities, sourceMode, observedAt, oddsObservedAt, showLabels = true }: {
  odds?: Odds | null
  probabilities?: Probabilities | null
  sourceMode?: string | null
  observedAt?: string | null
  oddsObservedAt?: string | null
  showLabels?: boolean
}) {
  const hasBookmakerOdds = Boolean(odds && [odds.home, odds.draw, odds.away].every((price) => Number.isFinite(price) && price > 1))
  const hasModel = !hasBookmakerOdds && sourceMode === 'elo-only' && Boolean(probabilities)
  const p = hasBookmakerOdds ? computeImpliedProbs(odds) : (probabilities ?? { home: 0, draw: 0, away: 0 })
  const empty = p.home + p.draw + p.away === 0
  const prices = hasBookmakerOdds ? odds : (hasModel ? {
    home: 1 / p.home,
    draw: 1 / p.draw,
    away: 1 / p.away,
  } : null)
  const source = hasBookmakerOdds ? 'Buchmacherquote' : (hasModel ? 'Elo-Modellquote · nicht wettbar' : 'Nicht verfügbar')
  const effectiveObservedAt = hasBookmakerOdds ? oddsObservedAt : observedAt
  const freshness = effectiveObservedAt ? new Intl.DateTimeFormat('de-CH', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(new Date(effectiveObservedAt)) : null
  return (
    <div className="w-full">
      <div className="mb-2 text-center text-xs leading-tight text-fg-2" title={effectiveObservedAt ?? undefined}>
        {source}{freshness ? ` · ${freshness}` : ''}
      </div>
      <div className="flex h-2 w-full gap-0.5 overflow-hidden rounded-full">
        {empty ? (
          <div className="h-full w-full bg-surface-2" />
        ) : (
          <>
            <div className="h-full rounded-l-full bg-blue-a transition-all" style={{ width: `${p.home * 100}%` }} />
            <div className="h-full bg-fg-3/50 transition-all" style={{ width: `${p.draw * 100}%` }} />
            <div className="h-full rounded-r-full bg-red-a transition-all" style={{ width: `${p.away * 100}%` }} />
          </>
        )}
      </div>
      {showLabels && (
        empty ? (
          <div className="mt-2 text-center text-xs text-fg-2">Keine Quoten oder Elo-Werte</div>
        ) : (
          <>
            <div className="mt-2 flex justify-between text-xs font-semibold tabular-nums">
              <span className="text-blue-a">{pct(p.home)}</span>
              <span className="text-fg-3">{pct(p.draw)} X</span>
              <span className="text-red-a">{pct(p.away)}</span>
            </div>
            <div className="mt-1 flex justify-between text-xs tabular-nums text-fg-2">
              <span>1&nbsp; {prices!.home.toFixed(2)}</span>
              <span>X&nbsp; {prices!.draw.toFixed(2)}</span>
              <span>2&nbsp; {prices!.away.toFixed(2)}</span>
            </div>
          </>
        )
      )}
    </div>
  )
}
