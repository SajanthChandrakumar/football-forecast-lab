import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import type { Match } from '../../lib/types'
import { kickoffTime } from '../../lib/format'
import { ProbBar } from '../../components/shared/ProbBar'
import { FormBadges, TeamLabel, TipBadge } from '../../components/shared/Badges'
import { MatchHintCard } from '../../components/shared/MatchHintCard'
import { staggerItem } from '../../components/shared/PageTransition'

function displayTeamName(team: string, display?: string): string {
  return display?.replace(/^\p{RI}\p{RI}\s*/u, '') || team
}

/** Shared fixture row — used by Dashboard and Value Bets. */
export function FixtureRow({ match, trailing }: { match: Match; trailing?: React.ReactNode }) {
  const navigate = useNavigate()
  const ct = match.raw_match?.commence_time
  const isPlayed = Boolean(match.completed || match.actual_score)

  return (
    <motion.div
      variants={staggerItem}
      className="glass-hover group w-full min-h-[48px] border-b border-line last:border-b-0"
    >
      <button
        type="button"
        onClick={() => navigate(`/match/${match.id}`)}
        aria-label={`${displayTeamName(match.home_team, match.home_disp)} gegen ${displayTeamName(match.away_team, match.away_disp)}`}
        className="w-full min-h-[48px] p-4 text-left sm:grid sm:grid-cols-[52px_1fr_auto_16px] sm:items-center sm:gap-4 sm:px-4 sm:py-3.5"
      >
        <span className="mb-3 flex items-center justify-between text-sm tabular-nums text-fg-3 sm:mb-0 sm:block">
          <span className="text-[10px] font-bold uppercase tracking-wider sm:hidden">Anstoß</span>
          {kickoffTime(ct)}
        </span>

        <span className="min-w-0">
          <span className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
            <span className="flex min-w-0 flex-1 flex-col items-start gap-1 sm:items-end sm:text-right">
              <TeamLabel name={match.home_team} disp={match.home_disp} logo={match.home_logo} />
              <FormBadges form={match.home_form} />
            </span>
            <span className="hidden w-40 shrink-0 sm:block">
              {isPlayed ? (
                <span className="flex items-center justify-center">
                  <span className="display-num rounded-lg border border-line-2 bg-surface-2 px-3 py-0.5 text-base text-fg">
                    {match.actual_score ?? '–'}
                  </span>
                </span>
              ) : (
                <ProbBar
                  odds={match.odds}
                  probabilities={match.probabilities}
                  sourceMode={match.source_mode}
                  observedAt={match.observed_at}
                  oddsObservedAt={match.odds_observed_at}
                />
              )}
            </span>
            <span className="flex min-w-0 flex-1 flex-col items-start gap-1">
              <TeamLabel name={match.away_team} disp={match.away_disp} logo={match.away_logo} />
              <FormBadges form={match.away_form} />
            </span>
          </span>
        </span>

        <span className="hidden sm:block">
          {trailing ?? (
            isPlayed ? (
              <span className="text-right">
                <span className="block text-[9px] font-bold uppercase tracking-wider text-fg-3">Algo</span>
                <TipBadge tip={match.top_tip} className="!px-2 !py-0.5 !text-sm" />
              </span>
            ) : (
              <TipBadge tip={match.top_tip} />
            )
          )}
        </span>
        <span className="hidden text-fg-3 sm:block">›</span>
      </button>

      <div className="px-4 pb-4 sm:hidden">
        <div className="rounded-xl bg-surface-2 p-3">
          <span className="flex items-center justify-between gap-3">
            <span className="text-xs font-bold uppercase tracking-wider text-fg-3">Unser Tipp</span>
            <TipBadge tip={match.top_tip} highlight />
          </span>
          {isPlayed && <span className="mt-2 block text-sm font-semibold text-fg">Endstand: {match.actual_score ?? '–'}</span>}
          <div className="mt-3"><MatchHintCard match={match} /></div>
        </div>
        {trailing && <div data-mobile-trailing className="mt-3 flex justify-end">{trailing}</div>}
      </div>
    </motion.div>
  )
}
