import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import type { Match } from '../../lib/types'
import { fixtureStatus } from '../../lib/fixture-status.mjs'
import { kickoffTime, shortDate } from '../../lib/format'
import { ProbBar } from '../../components/shared/ProbBar'
import { FormBadges, TeamLabel, TipBadge } from '../../components/shared/Badges'
import { MatchHintCard } from '../../components/shared/MatchHintCard'
import { staggerItem } from '../../components/shared/PageTransition'

/** Shared fixture card — used by Dashboard and Value Bets. */
export function FixtureRow({
  match,
  trailing,
  pendingResult = false,
  now,
}: {
  match: Match
  trailing?: React.ReactNode
  pendingResult?: boolean
  now?: number
}) {
  const ct = match.raw_match?.commence_time
  const status = pendingResult ? 'pending' : fixtureStatus(match, now)
  const isPlayed = status === 'played'
  const isPending = status === 'pending'
  const isUnscheduled = status === 'unscheduled'
  const canShowTip = status === 'upcoming' || isPlayed

  return (
    <motion.article
      variants={staggerItem}
      className="glass-hover overflow-hidden rounded-2xl border border-line bg-surface shadow-sm transition-colors"
    >
      <div className="grid lg:grid-cols-[minmax(0,1.1fr)_minmax(18rem,0.9fr)]">
        <div className="p-4 sm:p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <span className="block text-[10px] font-bold uppercase tracking-[0.16em] text-fg-3">Anstoß</span>
              <span className="mt-0.5 block text-sm font-semibold tabular-nums text-fg-2">
                {ct && Number.isFinite(Date.parse(ct)) ? `${shortDate(ct)} · ${kickoffTime(ct)}` : 'Zeit noch offen'}
              </span>
            </div>
            {isPending && <span className="rounded-full border border-amber-a/30 bg-amber-a/10 px-2.5 py-1 text-[10px] font-bold text-amber-a">Ergebnis ausstehend</span>}
            {isUnscheduled && <span className="rounded-full border border-line px-2.5 py-1 text-[10px] font-semibold text-fg-3">Anstoß offen</span>}
            {isPlayed && <span className="rounded-full border border-line px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-fg-3">Gespielt</span>}
          </div>

          <div className="mt-5 grid grid-cols-[minmax(0,1fr)_minmax(4.5rem,7rem)_minmax(0,1fr)] items-center gap-2 sm:mt-6 sm:gap-4">
            <div className="min-w-0 text-left">
              <TeamLabel name={match.home_team} disp={match.home_disp} logo={match.home_logo} wrap className="justify-start text-left text-base sm:text-xl" />
              <FormBadges form={match.home_form} className="mt-2" />
            </div>
            <div className="text-center">
              {isPlayed ? (
                <span className="display-num inline-flex min-w-16 justify-center rounded-xl border border-line-2 bg-surface-2 px-3 py-1 text-xl text-fg sm:text-2xl">
                  {match.actual_score ?? '–'}
                </span>
              ) : isPending ? (
                <span className="text-[10px] font-bold uppercase leading-tight tracking-wider text-fg-3">Ergebnis<br />offen</span>
              ) : (
                <span className="font-display text-xs font-bold uppercase tracking-widest text-fg-3">vs</span>
              )}
            </div>
            <div className="min-w-0">
              <TeamLabel name={match.away_team} disp={match.away_disp} logo={match.away_logo} wrap className="justify-end text-right text-base sm:text-xl" />
              <FormBadges form={match.away_form} className="mt-2" />
            </div>
          </div>

          {status === 'upcoming' && (
            <div className="mx-auto mt-5 max-w-sm">
              <ProbBar
                odds={match.odds}
                probabilities={match.probabilities}
                sourceMode={match.source_mode}
                observedAt={match.observed_at}
                oddsObservedAt={match.odds_observed_at}
              />
            </div>
          )}
        </div>

        <div className="flex flex-col justify-between gap-2 border-t border-line bg-surface-2/35 p-4 lg:border-l lg:border-t-0 lg:p-5">
          {canShowTip ? (
            <>
              <div className="flex items-center justify-between gap-3">
                <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-fg-3">
                  Modelltipp
                </span>
                <TipBadge tip={match.top_tip} highlight />
              </div>
              <div className="border-t border-line pt-2">
                <span className="mb-1 block text-[10px] font-bold uppercase tracking-[0.16em] text-fg-3">Quotenlage</span>
                <MatchHintCard match={match} compact />
              </div>
              {trailing && <div className="flex justify-end border-t border-line pt-2">{trailing}</div>}
              <Link
                to={`/match/${match.id}`}
                aria-label={`${isPlayed ? 'Analyse ansehen' : 'Tipp ansehen'}: ${match.home_team} gegen ${match.away_team}`}
                className="mt-auto inline-flex min-h-11 items-center justify-between rounded-xl border border-emerald-a/30 bg-emerald-dim px-4 py-2.5 text-sm font-bold text-emerald-a transition hover:border-emerald-a/60 hover:bg-emerald-dim/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-a/50"
              >
                <span>{isPlayed ? 'Analyse ansehen' : 'Tipp ansehen'}</span>
                <span aria-hidden="true" className="text-lg">→</span>
              </Link>
            </>
          ) : (
            <div role="status" className="my-auto rounded-xl border border-line bg-surface px-3 py-3">
              <p className="text-sm font-bold text-fg">{isPending ? 'Ergebnis ausstehend' : 'Anstoßzeit nicht verfügbar'}</p>
              <p className="mt-1 text-xs leading-relaxed text-fg-3">
                {isPending
                  ? 'Der Anstoß liegt zurück. Das Ergebnis ist noch nicht erfasst; die Auswertung folgt, sobald es vorliegt.'
                  : 'Für dieses Spiel ist noch keine verlässliche Anstoßzeit hinterlegt.'}
              </p>
            </div>
          )}
          {trailing && !canShowTip && <div className="flex justify-end border-t border-line pt-2">{trailing}</div>}
        </div>
      </div>
    </motion.article>
  )
}
