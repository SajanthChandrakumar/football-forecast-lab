import type { Probabilities } from '../../lib/types'
import { formatObservedAt } from '../../lib/observed-at.mjs'

export function OutcomeBar({ probabilities, homeTeam = 'Heim', awayTeam = 'Auswärts', sourceLabel, observedAt, compact = false, basisLabel }: {
  probabilities?: Probabilities | null
  homeTeam?: string
  awayTeam?: string
  sourceLabel?: string
  observedAt?: string | null
  compact?: boolean
  basisLabel?: string
}) {
  const values = probabilities && [probabilities.home, probabilities.draw, probabilities.away]
  const valid = values && values.every(value => Number.isFinite(value) && value >= 0 && value <= 1)
  const total = valid ? values.reduce((sum, value) => sum + value, 0) : 0
  if (!valid || !total) return <p className="outcome-unavailable">Spielausgangschancen nicht verfügbar.</p>
  const labels = [homeTeam, 'Remis', awayTeam]
  const names = ['home', 'draw', 'away']
  return <div className={compact ? 'outcome-summary compact' : 'outcome-summary'}>
    <div role="img" aria-label={`${basisLabel ? `${basisLabel}. ` : ''}Spielausgangschancen: ${labels.map((label, index) => `${label} ${Math.round(values[index] * 100)}%`).join(', ')}`} className="outcome-bar">
      {values.map((value, index) => <span key={names[index]} className={`outcome-${names[index]}`} style={{ width: `${value / total * 100}%` }} />)}
    </div>
    <div className="outcome-labels">
      {values.map((value, index) => <span key={names[index]}><span className="outcome-team">{labels[index]}</span><strong>{Math.round(value * 100)}%</strong></span>)}
    </div>
    {sourceLabel && <p className="outcome-source">{sourceLabel}{observedAt !== undefined && ` · ${formatObservedAt(observedAt)}`}</p>}
  </div>
}
