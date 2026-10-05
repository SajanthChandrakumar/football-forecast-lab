import type { Match, Prediction } from '../../lib/types'
import { buildMatchDataStatus } from '../../lib/match-data'
import { formatObservedAt } from '../../lib/observed-at.mjs'

export function MatchDataStatus({ match, prediction, now = Date.now(), compact = false, badge = false }: { match: Match; prediction?: Prediction; now?: number; compact?: boolean; badge?: boolean }) {
  const data = buildMatchDataStatus(match, now, prediction)
  const color = data.status === 'fresh' ? 'text-emerald-a' : data.status === 'stale' ? 'text-amber-a' : 'text-fg-2'
  if (badge) return <span className={`status-label ${color}`}><span aria-hidden="true" className="status-dot" />{data.title}</span>
  const content = <>
    <dl className="data-source-grid">
      {data.rows.map(row => {
        const observed = formatObservedAt(row.observedAt, now)
        return <div key={row.key} className="data-source-card">
          <dt>{row.label}</dt>
          <dd className={`data-source-state ${row.status === 'fresh' ? 'text-emerald-a' : ['stale', 'failed'].includes(row.status) ? 'text-amber-a' : 'text-fg-2'}`}><span aria-hidden="true" className="status-dot" />{row.message}</dd>
          <dd className="data-source-age" title={observed}>{row.source} · {observed.split(' · ').at(-1)}</dd>
        </div>
      })}
    </dl>
    <details className="info-disclosure">
      <summary>Was bedeutet die Datenlage?</summary>
      <div className="info-content">
        <p>{data.explanation}</p>
        <ul className="mt-2 space-y-1">{data.rows.map(row => <li key={row.key}>{row.label}: {formatObservedAt(row.observedAt, now)}</li>)}</ul>
        <p className="mt-2">Aufstellungen ergänzen die Spielanalyse. Ihre Anzeige bestätigt nicht, dass sie in den Modelltipp eingeflossen sind.</p>
      </div>
    </details>
  </>
  if (compact) return <details className="fixture-data">
    <summary className={color}><span aria-hidden="true" className="status-dot" />Datenlage: {data.title}<span aria-hidden="true" className="disclosure-arrow">⌄</span></summary>
    <div className="pb-2">{content}</div>
  </details>
  return <section aria-label="Datenlage" className="match-data-panel">
    <div className="match-data-heading"><h3>Datenlage</h3><span className={`status-label ${color}`}><span aria-hidden="true" className="status-dot" />{data.title}</span></div>
    {content}
  </section>
}
