import { Link } from 'react-router-dom'
import type { Match } from '../../lib/types'
import { fixtureStatus } from '../../lib/fixture-status.mjs'
import { kickoffTime, shortDate } from '../../lib/format'
import { TeamLogo } from '../../components/shared/Badges'
import { MatchDataStatus } from '../../components/shared/MatchDataStatus'
import { SharedTipEditor } from '../../components/shared/SharedTipEditor'
import type { CompetitionId } from '../../lib/types'
import { buildMatchHint } from '../../lib/matchHint'
import { OutcomeBar } from '../../components/shared/OutcomeBar'

export function FixtureRow({ match, trailing, pendingResult = false, now, compact = false, sharedTipMode = false, competition, savedTip, autoFocusTip = false, onTipAutoFocus, onSaveAndNext, onSaveStart, onTipSaved }: {
  match: Match; trailing?: React.ReactNode; pendingResult?: boolean; now?: number; compact?: boolean
  sharedTipMode?: boolean; competition?: CompetitionId; savedTip?: string | null
  autoFocusTip?: boolean; onTipAutoFocus?: () => void; onSaveAndNext?: () => void; onSaveStart?: () => void; onTipSaved?: (tip: string) => void
}) {
  const ct = match.raw_match?.commence_time
  const status = pendingResult ? 'pending' : fixtureStatus(match, now)
  const clubCalculationPending = (competition === 'epl2026' || competition === 'ucl2026') && match.calculation_status === 'pending'
  const hasTip = Boolean(match.top_tip && match.top_tip !== 'N/A')
  const dated = ct && Number.isFinite(Date.parse(ct))
  const hint = buildMatchHint(match, now ?? Date.now(), competition === 'epl2026' || competition === 'ucl2026')
  const statusLabel = status === 'played' ? 'Abgeschlossen' : status === 'pending' ? 'Ergebnis ausstehend' : status === 'unscheduled' ? 'Anstoß offen' : 'Demnächst'
  const pickLabel = status === 'played' ? 'Ergebnis' : 'Modelltipp'
  const pick = status === 'played' ? match.actual_score ?? '–' : status === 'upcoming' && !clubCalculationPending && hasTip ? match.top_tip : '–'
  return <article className={`match-card${compact ? ' match-card-compact' : ''}`}>
    <header className="match-card-top">
      <div className="match-card-time">
        <span>{dated ? kickoffTime(ct) : '–'}</span>
        <span className="match-card-date">{dated ? shortDate(ct) : 'Anstoß offen'}</span>
      </div>
      <span className={`match-card-status match-card-status-${status}`}>{statusLabel}</span>
    </header>

    <div className="match-card-scoreboard">
      <div className="match-card-team match-card-team-home">
        <TeamLogo name={match.home_team} src={match.home_logo} className="match-card-logo h-8 w-8 shrink-0 sm:h-10 sm:w-10" />
        <span className="match-card-team-name">{match.home_disp || match.home_team}</span>
      </div>
      <div className="match-card-center">
        <span className="match-card-pick-label">{pickLabel}</span>
        <strong className="match-card-pick-value">{pick}</strong>
      </div>
      <div className="match-card-team match-card-team-away">
        <TeamLogo name={match.away_team} src={match.away_logo} className="match-card-logo h-8 w-8 shrink-0 sm:h-10 sm:w-10" />
        <span className="match-card-team-name">{match.away_disp || match.away_team}</span>
      </div>
    </div>

    {status === 'played' && <p className="match-card-note">{hasTip ? `Modelltipp: ${match.top_tip}` : 'Keine Vorab-Empfehlung'}</p>}
    {status === 'upcoming' && savedTip?.trim() && <p className="match-card-note">Gemeinsamer Tipp: {savedTip}</p>}

    {status !== 'played' && <div className="match-card-outcome">
      {clubCalculationPending
        ? <p role="status" className="outcome-unavailable">Analyse wird vorbereitet.</p>
        : <OutcomeBar
          probabilities={hint.probabilities}
          homeTeam={match.home_disp || match.home_team}
          awayTeam={match.away_disp || match.away_team}
          sourceLabel={hint.sourceLabel}
          observedAt={hint.observedAt}
          compact
        />}
    </div>}

    {status === 'upcoming' && <div className="match-card-data"><MatchDataStatus match={match} now={now} compact /></div>}
    {(status === 'upcoming' || status === 'played') && <Link to={`/match/${match.id}`} state={{ fromFixtureList: true }} aria-label={`${status === 'played' ? 'Analyse ansehen' : 'Tipp ansehen'}: ${match.home_team} gegen ${match.away_team}`} className="match-card-action min-h-11"><span className="match-card-action-label">{status === 'played' ? 'Spielanalyse' : 'Tipp ansehen'}</span><span aria-hidden="true" className="fixture-action-icon"><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-3.5 w-3.5"><path d="M4 10h12m-5-5 5 5-5 5" /></svg></span></Link>}
    {trailing != null && <div className="match-card-footer">{trailing}</div>}
    {sharedTipMode && competition && now != null && <div className="match-card-editor"><SharedTipEditor key={`${competition}:${match.id}`} match={match} competition={competition} savedTip={savedTip} now={now} compact autoFocus={autoFocusTip} onAutoFocus={onTipAutoFocus} onSaveAndNext={onSaveAndNext} onSaveStart={onSaveStart} onSaved={onTipSaved} /></div>}
  </article>
}
