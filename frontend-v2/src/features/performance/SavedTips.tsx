import { useState } from 'react'
import { Link } from 'react-router-dom'
import { GlassCard, SectionTitle } from '../../components/shared/GlassCard'
import { kickoffTime, shortDate } from '../../lib/format'
import type { Archive } from '../../lib/types'

export function SavedTips({ archive, now }: { archive: Archive; now: number }) {
  const [limit, setLimit] = useState(12)
  const pending = Object.entries(archive).filter(([, entry]) =>
    typeof entry.prediction?.user_tip === 'string' && entry.prediction.user_tip.trim()
    && entry.post_match_result?.status !== 'completed' && !entry.post_match_result?.actual_score,
  ).sort(([, a], [, b]) => (a.metadata?.commence_time ?? '').localeCompare(b.metadata?.commence_time ?? ''))

  return <section aria-label="Gespeicherte Tipps">
    <GlassCard>
      <SectionTitle className="mb-3">Gespeicherte Tipps</SectionTitle>
      {pending.length ? <>
        <div className="grid gap-3 sm:grid-cols-2">
          {pending.slice(0, limit).map(([id, entry]) => {
            const kickoff = entry.metadata?.commence_time
            const timestamp = Date.parse(kickoff ?? '')
            return <article key={id} className="rounded-lg border border-line bg-surface-2 p-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <Link to={`/match/${encodeURIComponent(id)}`} className="min-w-0 text-sm font-semibold text-fg underline decoration-line-2 underline-offset-4">{entry.metadata.home_team} – {entry.metadata.away_team}</Link>
                <strong className="text-lg tabular-nums text-fg">{entry.prediction.user_tip}</strong>
              </div>
              <div className="mt-2 flex flex-wrap justify-between gap-2 text-xs text-fg-2">
                <span>{Number.isFinite(timestamp) ? `${shortDate(kickoff)} · ${kickoffTime(kickoff)}` : 'Anstoßzeit fehlt'}</span>
                <span>{Number.isFinite(timestamp) && timestamp <= now ? 'Ergebnis ausstehend' : 'Gespeichert'}</span>
              </div>
            </article>
          })}
        </div>
        {pending.length > limit && <button type="button" onClick={() => setLimit(value => value + 12)} className="mt-3 min-h-11 rounded-lg border border-line px-3 text-sm text-fg-2">Weitere gespeicherte Tipps anzeigen ({pending.length - limit})</button>}
      </> : <p className="text-sm text-fg-2">Noch keine gespeicherten Tipps für anstehende Spiele. Abgeschlossene Tipps findest du unter „Punkte & Verlauf“.</p>}
    </GlassCard>
  </section>
}
