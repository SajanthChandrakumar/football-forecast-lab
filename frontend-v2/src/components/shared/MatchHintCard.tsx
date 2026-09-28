import type { Match } from '../../lib/types'
import { buildMatchHint } from '../../lib/matchHint'
import { cn } from '../../lib/util'

export function MatchHintCard({ match, compact = false }: { match: Match; compact?: boolean }) {
  const hint = buildMatchHint(match)

  return (
    <div>
      {hint.available && (
        <span className={cn('text-fg-2', compact ? 'text-xs' : 'text-sm')}>
          Tendenz beim Spielausgang: {hint.confidenceLabel}
        </span>
      )}
      <p className={cn('leading-snug text-fg', compact ? 'text-sm' : 'text-base', hint.available && 'mt-2')}>
        {hint.summary}
      </p>
      <p className={cn('mt-1 text-fg-3', compact ? 'text-xs' : 'text-sm')}>{hint.sourceLabel}</p>

      {!compact && hint.reasons.length > 0 && (
        <details className="group/hint mt-2 border-t border-line pt-1">
        <summary className={cn('flex min-h-11 cursor-pointer list-none items-center justify-between font-medium text-fg-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-a', compact ? 'text-sm' : 'text-base')}>
            Warum?
            <span aria-hidden="true" className="text-lg transition-transform group-open/hint:rotate-90">›</span>
          </summary>
          <ul className={cn('space-y-2 pb-1 leading-relaxed text-fg-2', compact ? 'text-xs' : 'text-base')}>
            {hint.reasons.map((reason) => <li key={reason}>• {reason}</li>)}
          </ul>
        </details>
      )}
    </div>
  )
}
