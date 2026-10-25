import { useEffect, useMemo, useState } from 'react'
import { clubFormHomeAwayScore, clubFormSummary, verifiedClubFormMatches } from '../../lib/team-form.mjs'
import { formatObservedAt } from '../../lib/observed-at.mjs'
import type { TeamForm, TeamFormMatch } from '../../lib/types'

type CompetitionFilter = 'all' | 'league' | 'cup' | 'europe'
const FILTERS: { value: CompetitionFilter; label: string }[] = [
  { value: 'all', label: 'Alle Pflichtspiele' },
  { value: 'league', label: 'Liga' },
  { value: 'cup', label: 'Pokal' },
  { value: 'europe', label: 'Europa' },
]
const COMPETITION_LABEL = { league: 'Liga', cup: 'Pokal', europe: 'Europapokal' }
const RESULT_LABEL = { W: 'Sieg', D: 'Unentschieden', L: 'Niederlage' }
const RESULT_MARK = { W: 'S', D: 'U', L: 'N' }

function sourceLabel(source?: string) {
  return source === 'espn+fotmob' ? 'ESPN + FotMob'
    : source === 'espn' ? 'ESPN'
      : source === 'api_football' ? 'API-Football'
        : source
}

export function ClubTeamFormHistory({ team, form, beforeKickoff }: { team: string; form?: TeamForm | null; beforeKickoff?: string | null }) {
  const [competition, setCompetition] = useState<CompetitionFilter>('all')
  const [expanded, setExpanded] = useState(false)
  const matches = useMemo(() => verifiedClubFormMatches(form, { before: beforeKickoff, competition }), [form, beforeKickoff, competition])
  const visible = matches.slice(0, expanded ? 10 : 5)
  const summary = clubFormSummary(visible)
  const hasCompleteScores = visible.length > 0 && visible.every((match) => Number.isFinite(match.goals_for) && Number.isFinite(match.goals_against))
  const cutoffUnknown = beforeKickoff != null && !Number.isFinite(Date.parse(beforeKickoff))

  return <section className="rounded-xl border border-line bg-surface p-4 text-left" aria-label={`${team} Pflichtspielform`}>
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div>
        <h3 className="text-base font-bold text-fg">{team}</h3>
        <p className="mt-1 text-xs text-fg-2">Geprüfte Pflichtspiele · alle Wettbewerbe{sourceLabel(form?.source) ? ` · Quelle: ${sourceLabel(form?.source)}` : ''}</p>
      </div>
      {form?.status === 'stale' && <span className="text-xs font-semibold text-amber-a">Formdaten älter</span>}
    </div>
    {form?.coverage && <p className="mt-2 text-xs text-fg-3">Abdeckung: {form.coverage.available} von {form.coverage.required} geprüften Spielen{form.observed_at ? ` · Stand ${formatObservedAt(form.observed_at)}` : ''}</p>}
    {form?.scope !== 'all_competitions' && <p className="mt-3 rounded-lg bg-surface-2 px-3 py-2 text-xs text-fg-2">Für diese Ansicht liegen noch keine geprüften Formdaten aus allen Wettbewerben vor.</p>}
    {form?.scope === 'all_competitions' && <>
      <div role="group" aria-label={`${team}: Form nach Wettbewerb`} className="mt-3 flex flex-wrap gap-2">
        {FILTERS.map((item) => <button key={item.value} type="button" aria-pressed={competition === item.value} onClick={() => { setCompetition(item.value); setExpanded(false) }} className={`min-h-11 rounded-full border px-3 text-xs font-semibold ${competition === item.value ? 'border-action bg-action text-on-action' : 'border-line text-fg-2 hover:bg-surface-2'}`}>{item.label}</button>)}
      </div>
      {visible.length > 0 ? <>
        <dl className="mt-3 grid grid-cols-2 gap-2 text-center sm:grid-cols-4">
          <Metric label="Spiele" value={`${visible.length}${matches.length > visible.length ? ` von ${matches.length}` : ''}`} />
          <Metric label="Siege · Remis · Niederlagen" value={`${summary.wins} · ${summary.draws} · ${summary.losses}`} />
          {hasCompleteScores && <Metric label="Tore" value={`${summary.goalsFor}:${summary.goalsAgainst}`} />}
        </dl>
        <ol className="mt-3 space-y-2">
          {visible.map((match) => <ClubFormMatchRow key={match.fixture_id} match={match} />)}
        </ol>
        {matches.length > 5 && <button type="button" onClick={() => setExpanded((value) => !value)} className="mt-2 min-h-11 text-sm font-semibold text-accent underline underline-offset-4">{expanded ? 'Weniger Spiele' : `Weitere Spiele (${Math.min(10, matches.length)})`}</button>}
      </> : <p role="status" className="mt-3 text-sm text-fg-2">{cutoffUnknown ? 'Der Anstoßzeitpunkt fehlt; Formspiele lassen sich zeitlich nicht sicher zuordnen.' : 'Für diesen Filter sind keine geprüften Formspiele verfügbar.'}</p>}
    </>}
  </section>
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="rounded-lg bg-surface-2 px-2 py-2"><dt className="text-[11px] text-fg-3">{label}</dt><dd className="mt-1 font-bold tabular-nums text-fg">{value}</dd></div>
}

function scoreText(score?: { home: number; away: number }) {
  return score && Number.isFinite(score.home) && Number.isFinite(score.away) ? `${score.home}:${score.away}` : null
}

function ClubFormMatchRow({ match }: { match: TeamFormMatch }) {
  const home = match.home_team!
  const away = match.away_team!
  const isHome = match.venue === 'home'
  const isAway = match.venue === 'away'
  const displayedScore = clubFormHomeAwayScore(match) ?? match.score
  const result = match.result
  const resultClass = result === 'W' ? 'text-emerald-a' : result === 'L' ? 'text-red-a' : 'text-fg-2'
  return <li className="rounded-lg border border-line bg-surface-2 px-3 py-2.5">
    <div className="grid grid-cols-[minmax(0,1fr)_auto] grid-rows-2 items-center gap-x-3 gap-y-1 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] sm:grid-rows-1 sm:gap-2">
      <ClubSide name={home} logo={match.home_logo} selected={isHome} align="left" className="col-start-1 row-start-1" />
      <span className="col-start-2 row-span-2 row-start-1 text-center font-bold tabular-nums text-fg sm:row-span-1">{displayedScore}</span>
      <ClubSide name={away} logo={match.away_logo} selected={isAway} align="right" className="col-start-1 row-start-2 sm:col-start-3 sm:row-start-1" />
    </div>
    <div className="mt-2 flex flex-wrap items-center justify-between gap-x-2 gap-y-1 text-xs text-fg-2">
      <span>{new Date(match.played_at).toLocaleString('de-CH', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Zurich' })} · {match.competition_name} · {COMPETITION_LABEL[match.competition_kind!]}</span>
      <span className={`font-bold ${resultClass}`} aria-label={RESULT_LABEL[result]}>{RESULT_MARK[result]} · {RESULT_LABEL[result]}</span>
    </div>
    {match.result_type && match.result_type !== 'FT' && <p className="mt-1 text-xs text-fg-3">
      {match.score_90 && `Nach 90 Min. ${scoreText(match.score_90)}`}
      {match.result_type === 'AET' && ` · Nach Verlängerung ${scoreText(match.score_aet) ?? displayedScore}`}
      {match.result_type === 'PEN' && ` · Elfmeterschießen ${scoreText(match.penalties) ?? 'Ergebnis nicht übermittelt'}`}
    </p>}
  </li>
}

function ClubSide({ name, logo, selected, align, className }: { name: string; logo?: string | null; selected: boolean; align: 'left' | 'right'; className: string }) {
  return <span role="group" aria-label={`${name}, ${selected ? 'ausgewählte Mannschaft' : 'Gegner'}`} className={`flex min-w-0 items-center gap-2 ${align === 'right' ? 'sm:flex-row-reverse sm:justify-end sm:text-right' : ''} ${selected ? 'font-bold text-accent' : 'font-medium text-fg'} ${className}`}>
    <ClubCrest name={name} logo={logo} />
    <span className="min-w-0 flex-1 break-words">{name}</span>
  </span>
}

function ClubCrest({ name, logo }: { name: string; logo?: string | null }) {
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [logo])
  if (logo && !failed) return <img src={logo} alt={`${name} Wappen`} onError={() => setFailed(true)} className="h-7 w-7 shrink-0 object-contain" />
  return <span role="img" aria-label={`${name}: Wappen nicht verfügbar`} className="grid h-7 w-7 shrink-0 place-items-center rounded-full border border-line bg-surface text-[10px] text-fg-3">⚽</span>
}
