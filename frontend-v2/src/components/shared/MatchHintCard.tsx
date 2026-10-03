import type { Match } from '../../lib/types'
import { buildMatchHint } from '../../lib/matchHint'
import { formatObservedAt } from '../../lib/observed-at.mjs'
import { cn } from '../../lib/util'

const confidenceStyle = {
  high: 'bg-emerald-dim text-emerald-a',
  medium: 'bg-blue-a/10 text-blue-a',
  low: 'bg-orange-a/10 text-orange-a',
} as const

export function MatchHintCard({ match, compact = false }: { match: Match; compact?: boolean }) {
  const hint = buildMatchHint(match)
  const badgeStyle = hint.confidence === 'unavailable' ? '' : confidenceStyle[hint.confidence]

  return (
    <div>
      {hint.available && (
        <span className={cn(compact ? cn('inline-flex rounded-full px-2.5 py-1 text-xs font-bold', badgeStyle) : 'text-sm font-semibold text-emerald-a')}>
          Spielausgangstendenz (Sieg/Remis/Niederlage): {hint.confidenceLabel}
        </span>
      )}
      <p className={cn('leading-snug text-fg', compact ? 'text-sm font-semibold' : 'text-base font-medium', hint.available && 'mt-2')}>
        {hint.summary}
      </p>
      {hint.probabilities && <div className={cn('mt-2 grid grid-cols-3 gap-2 text-fg-2', compact ? 'text-[10px]' : 'text-xs')} aria-label="Wahrscheinlichkeiten für Sieg, Remis und Niederlage">
        <span className="min-w-0"><b className="block text-fg">{Math.round(hint.probabilities.home * 100)}%</b>{match.home_disp || match.home_team}</span>
        <span className="min-w-0"><b className="block text-fg">{Math.round(hint.probabilities.draw * 100)}%</b>Unentschieden</span>
        <span className="min-w-0"><b className="block text-fg">{Math.round(hint.probabilities.away * 100)}%</b>{match.away_disp || match.away_team}</span>
      </div>}
      <p className={cn('mt-1 text-fg-3', compact ? 'text-[10px]' : 'text-xs')}>Quelle: {hint.sourceLabel} · {formatObservedAt(hint.observedAt)}</p>
      {!compact && <p className="mt-2 text-xs text-fg-3">Die Werte betreffen Sieg, Remis oder Niederlage und sagen nichts über ein exaktes Ergebnis aus.</p>}

      {!compact && hint.reasons.length > 0 && (
        <details className="group/hint mt-2 border-t border-line pt-1">
        <summary className={cn('flex min-h-11 cursor-pointer list-none items-center justify-between font-semibold text-emerald-a focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-a/50', compact ? 'text-sm' : 'text-base')}>
            Weitere verfügbare Hinweise
            <span aria-hidden="true" className="text-lg transition-transform group-open/hint:rotate-90">›</span>
          </summary>
          <p className="pb-2 text-xs leading-relaxed text-fg-3">Zusätzlicher Kontext; diese Angaben sind keine bestätigte Liste der Modelleingaben.</p>
          <ul className={cn('space-y-2 pb-1 leading-relaxed text-fg-2', compact ? 'text-xs' : 'text-base')}>
            {hint.reasons.map((reason) => <li key={reason}>• {reason}</li>)}
          </ul>
        </details>
      )}
    </div>
  )
}
