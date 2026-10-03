import { Link } from 'react-router-dom'
import type { Match } from '../../lib/types'
import { fixtureStatus } from '../../lib/fixture-status.mjs'
import { kickoffTime, shortDate } from '../../lib/format'
import { TeamLogo } from '../../components/shared/Badges'
import { MatchHintCard } from '../../components/shared/MatchHintCard'
import { SharedTipEditor } from '../../components/shared/SharedTipEditor'
import type { CompetitionId } from '../../lib/types'

export function FixtureRow({ match, trailing, pendingResult = false, now, compact = false, sharedTipMode = false, competition, savedTip, autoFocusTip = false, onTipAutoFocus, onSaveAndNext, onSaveStart, onTipSaved }: {
  match: Match; trailing?: React.ReactNode; pendingResult?: boolean; now?: number; compact?: boolean
  sharedTipMode?: boolean; competition?: CompetitionId; savedTip?: string | null
  autoFocusTip?: boolean; onTipAutoFocus?: () => void; onSaveAndNext?: () => void; onSaveStart?: () => void; onTipSaved?: (tip: string) => void
}) {
  const ct = match.raw_match?.commence_time
  const status = pendingResult ? 'pending' : fixtureStatus(match, now)
  const hasTip = Boolean(match.top_tip && match.top_tip !== 'N/A')
  const hasOdds = Boolean(match.odds && [match.odds.home, match.odds.draw, match.odds.away].every(price => Number.isFinite(price) && price > 1))
  const source = hasOdds ? 'Buchmacherquote' : match.probabilities ? 'Elo-Modell · nicht wettbar' : 'Daten fehlen'
  const dated = ct && Number.isFinite(Date.parse(ct))
  const sourceLabel = status === 'played' ? 'Abgeschlossen' : status === 'pending' ? 'Ergebnis ausstehend' : status === 'unscheduled' ? 'Anstoß offen' : source
  return <article className="fixture-row">
    <div className="fixture-time">{dated ? kickoffTime(ct) : '–'}<span className="fixture-date">{dated ? shortDate(ct) : 'Anstoß offen'}</span></div>
    <div className="fixture-teams">
      <div className="fixture-team"><TeamLogo name={match.home_team} src={match.home_logo} className="h-5 w-5 shrink-0" /><span className="fixture-team-name">{match.home_disp || match.home_team}</span></div>
      <div className="fixture-team"><TeamLogo name={match.away_team} src={match.away_logo} className="h-5 w-5 shrink-0" /><span className="fixture-team-name">{match.away_disp || match.away_team}</span></div>
    </div>
    <div className="fixture-source"><span className="fixture-source-dot" aria-hidden="true" />{sourceLabel}{status === 'played' && <span className="block">{hasTip ? `Modelltipp: ${match.top_tip}` : 'Keine Vorab-Empfehlung'}</span>}{status === 'upcoming' && savedTip?.trim() && <span className="block">Gemeinsamer Tipp: {savedTip}</span>}</div>
    <div className="fixture-score"><span className="fixture-score-label">{status === 'played' ? 'Ergebnis' : 'Modelltipp'}</span><strong className="fixture-score-value">{status === 'played' ? match.actual_score ?? '–' : status === 'upcoming' && hasTip ? match.top_tip : '–'}</strong></div>
    {(status === 'upcoming' || status === 'played') && <Link to={`/match/${match.id}`} state={{ fromFixtureList: true }} aria-label={`${status === 'played' ? 'Analyse ansehen' : 'Tipp ansehen'}: ${match.home_team} gegen ${match.away_team}`} className="fixture-action min-h-11"><span className="fixture-action-label">{status === 'played' ? 'Analyse ansehen' : 'Tipp ansehen'}</span><span aria-hidden="true" className="fixture-action-icon"><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-3.5 w-3.5"><path d="M4 10h12m-5-5 5 5-5 5" /></svg></span></Link>}
    {trailing != null && <div className="fixture-extra">{trailing}</div>}
    {sharedTipMode && competition && now != null && <div className="fixture-extra"><SharedTipEditor key={`${competition}:${match.id}`} match={match} competition={competition} savedTip={savedTip} now={now} compact autoFocus={autoFocusTip} onAutoFocus={onTipAutoFocus} onSaveAndNext={onSaveAndNext} onSaveStart={onSaveStart} onSaved={onTipSaved} /></div>}
    {!compact && status === 'upcoming' && <div className="fixture-hint"><MatchHintCard match={match} compact /></div>}
  </article>
}
