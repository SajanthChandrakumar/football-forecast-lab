import { useEffect, useMemo, useState } from 'react'
import { useMatches } from '../../hooks/queries'
import { useAppState } from '../../state/AppState'
import { cn } from '../../lib/util'
import { resolveInitialTeamSelection } from '../../lib/team-selection.mjs'
import { GlassCard, SectionTitle } from '../../components/shared/GlassCard'
import { TeamLogo } from '../../components/shared/Badges'
import { PageTransition, PageHeader } from '../../components/shared/PageTransition'
import { ChartSkeleton, CardGridSkeleton } from '../../components/shared/Skeleton'
import { QueryState } from '../../components/shared/QueryState'
import { useTeamFormData } from './useTeamFormData'
import { EloChart } from './EloChart'

const FORM_STYLE: Record<string, string> = {
  W: 'bg-emerald-dim text-emerald-a',
  D: 'bg-surface-2 text-fg-3',
  L: 'bg-red-a/10 text-red-a',
}

const FORM_LABEL = { W: 'Sieg', D: 'Unentschieden', L: 'Niederlage' } as const

export function TeamFormView() {
  const { rows, history, matchInfo, coverage, isLoading, error, retry } = useTeamFormData()
  const matchQuery = useMatches()
  const { data: fixtures, isLoading: matchesLoading } = matchQuery
  const { competition, selectedTeams: storedSelectedTeams, setSelectedTeams, toggleTeam } = useAppState()
  const storedTeams = storedSelectedTeams ?? null
  const leagueLabel = competition === 'epl2026' ? 'Premier-League' : 'UCL'
  const incompleteUclRatings = (competition === 'ucl2026' && !coverage.complete) || (competition === 'epl2026' && !coverage.standingsValid)
  const selectedTeams = (storedTeams ?? []).filter((team) => rows.some((row) => row.team === team)).slice(0, 4)
  const [search, setSearch] = useState('')

  useEffect(() => {
    if (matchesLoading || isLoading || error || rows.length === 0 || incompleteUclRatings) return
    if (storedTeams === null) {
      setSelectedTeams(resolveInitialTeamSelection(null, fixtures ?? [], rows))
      return
    }
    const resolved = resolveInitialTeamSelection(storedTeams, fixtures ?? [], rows)
    if (resolved.some((team, index) => team !== storedTeams[index]) || resolved.length !== storedTeams.length) setSelectedTeams(resolved)
  }, [storedTeams, matchesLoading, isLoading, error, rows, incompleteUclRatings, fixtures, setSelectedTeams])

  const filtered = useMemo(
    () => rows.filter((row) => row.team.toLocaleLowerCase().includes(search.toLocaleLowerCase())),
    [rows, search],
  )

  return (
    <PageTransition>
      <PageHeader title="Teamvergleich" subtitle="Elo-Verlauf und Resultate für bis zu vier Teams vergleichen." />
      <p className="mb-5 max-w-3xl rounded-xl border border-line bg-surface px-4 py-3 text-sm leading-relaxed text-fg-2">
        Elo beschreibt die relative Teamstärke. Die Ergebnisse stammen aus dem Wettbewerbsarchiv.
      </p>
      {competition === 'wc2026' && <p className="mb-4 text-xs text-fg-3">Gastgeber-Bonus: +80 Elo für USA, Kanada und Mexiko.</p>}

      {isLoading && <div className="space-y-4"><ChartSkeleton /><CardGridSkeleton count={1} cols="grid-cols-1" /></div>}
      {!isLoading && error && <QueryState title="Teamdaten konnten nicht geladen werden" message="Elo-Verlauf, Ratings oder Archivdaten sind derzeit nicht erreichbar." onRetry={() => void retry()} />}

      <div className={cn('space-y-4', (isLoading || error) && 'hidden')}>
        {incompleteUclRatings ? (
          <div role="alert" className="rounded-xl border border-amber-a/30 bg-amber-a/5 px-4 py-3 text-sm text-fg-2">
            {!coverage.standingsValid ? (
              <p>Teamvergleich nicht verfügbar, weil die vollständige offizielle {leagueLabel}-Tabelle fehlt.</p>
            ) : (
              <>
                <p>ClubElo-Werte liegen nur für {coverage.available} von {coverage.required} {leagueLabel}-Teams vor.</p>
                <p className="mt-1 text-xs text-fg-3">Fehlende Teams: {coverage.missing.join(', ')}</p>
              </>
            )}
          </div>
        ) : rows.length === 0 && <p className="rounded-xl border border-line bg-surface px-4 py-6 text-center text-sm text-fg-2">Keine Teamratings verfügbar.</p>}

        {competition === 'epl2026' && coverage.standingsValid && !coverage.complete && (
          <div role="alert" className="rounded-xl border border-amber-a/30 bg-amber-a/5 px-4 py-3 text-sm text-fg-2">
            <p>ClubElo-Ratings liegen nur für {coverage.available} von {coverage.required} Premier-League-Teams vor.</p>
            <p className="mt-1 text-xs text-fg-3">Fehlende Teams: {coverage.missing.join(', ')}</p>
          </div>
        )}
        {(competition === 'ucl2026' || competition === 'epl2026') && !incompleteUclRatings && coverage.showAlert && (
          <div role="status" className="rounded-xl border border-amber-a/30 bg-amber-a/5 px-4 py-3 text-sm text-fg-2">
            {coverage.snapshotAvailable < coverage.snapshotRequired
              ? `Aktuelle Ratings liegen nur für ${coverage.snapshotAvailable} von ${coverage.snapshotRequired} ${leagueLabel}-Teams vor. Angezeigt werden die letzten vollständigen Ratings.`
              : `Die Aktualität der ClubElo-Daten für ${leagueLabel} konnte nicht bestätigt werden. Angezeigt werden die verfügbaren lokalen Ratings.`}
            {coverage.error && <p className="mt-1 text-xs text-fg-3">Der Datenstatus ist derzeit nicht erreichbar.</p>}
            {coverage.snapshotMissing.length > 0 && <p className="mt-1 text-xs text-fg-3">Bei der letzten Aktualisierung fehlten: {coverage.snapshotMissing.join(', ')}</p>}
          </div>
        )}

        {!incompleteUclRatings && rows.length > 0 && <>
          <GlassCard>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <SectionTitle>Teams vergleichen</SectionTitle>
              <span className="text-xs text-fg-2">{selectedTeams.length} von 4 ausgewählt</span>
            </div>

            <div className="mb-5 space-y-3">
              {selectedTeams.length > 0 && <div role="group" aria-label="Ausgewählte Teams" className="flex flex-wrap gap-2">
                {selectedTeams.map((team) => <span key={team} className="inline-flex min-h-11 min-w-0 max-w-full items-center gap-2 rounded-full border border-line-2 bg-surface-2 py-1 pl-2.5 pr-1.5 text-xs font-medium text-fg">
                  <TeamLogo name={team} /><span className="min-w-0 break-words">{team}</span>
                  <button type="button" onClick={() => toggleTeam(team)} aria-label={`${team} aus dem Vergleich entfernen`} className="grid h-11 w-11 shrink-0 place-items-center rounded-full text-base text-fg-2 hover:bg-surface hover:text-fg">×</button>
                </span>)}
              </div>}
              <label htmlFor="team-form-search" className="block text-xs font-medium text-fg-2">Teams suchen und hinzufügen</label>
              <input
                id="team-form-search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Teamname eingeben"
                className="min-h-11 w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-fg outline-none placeholder:text-fg-3 focus:border-[var(--blue)] sm:max-w-xs"
              />
              <div className="flex max-h-48 flex-wrap gap-2 overflow-y-auto">
                {filtered.map((row) => {
                  const active = selectedTeams.includes(row.team)
                  const limitReached = selectedTeams.length >= 4
                  return <button
                    key={row.team}
                    type="button"
                    aria-pressed={active}
                    disabled={!active && limitReached}
                    onClick={() => toggleTeam(row.team)}
                    className={cn(
                      'min-h-11 rounded-lg border px-3 py-2 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-45',
                      active ? 'border-action bg-action text-on-action' : 'border-line bg-surface text-fg-2 hover:bg-surface-2',
                    )}
                  ><span className="inline-flex items-center gap-2"><TeamLogo name={row.team} />{row.team}</span></button>
                })}
                {filtered.length === 0 && <p className="text-sm text-fg-2">Kein passendes Team gefunden.</p>}
              </div>
            </div>

            {selectedTeams.length > 0 && <div className={cn('mb-5 grid gap-2 sm:grid-cols-2', selectedTeams.length === 1 ? 'lg:grid-cols-1' : selectedTeams.length === 2 ? 'lg:grid-cols-2' : 'lg:grid-cols-4')}>
              {selectedTeams.map((team) => {
                const row = rows.find((item) => item.team === team)
                if (!row) return null
                return <div key={team} className="min-w-0 rounded-lg border border-line bg-surface-2 px-3 py-3">
                  <div className="flex items-center gap-2 truncate text-sm font-medium text-fg"><TeamLogo name={team} /><span className="truncate">{team}</span></div>
                  <div className="mt-2 text-2xl font-semibold tabular-nums text-fg">{Math.round(row.elo)} <span className="text-xs font-normal text-fg-3">Elo</span></div>
                  <p className="mt-1 text-xs text-fg-2">Bilanz im Archiv: {row.w}-{row.d}-{row.l} aus {row.w + row.d + row.l} {row.w + row.d + row.l === 1 ? 'Spiel' : 'Spielen'}</p>
                  <p className="mt-1 text-xs text-fg-3">Siege · Remis · Niederlagen</p>
                  {row.w + row.d + row.l < 5 && <p className="mt-1 text-xs text-fg-3">Kleine Stichprobe: {row.w + row.d + row.l} {row.w + row.d + row.l === 1 ? 'abgeschlossenes Spiel' : 'abgeschlossene Spiele'}.</p>}
                  {row.recentGames.length > 0 ? <ol className="mt-2 space-y-1.5 text-xs text-fg-2">
                    {[...row.recentGames].reverse().map((game, index) => <li key={`${team}-${game.playedAt ?? 'unknown'}-${game.score}-${index}`} className="flex min-w-0 flex-wrap justify-between gap-x-2">
                      <span className="min-w-0">{game.playedAt && Number.isFinite(Date.parse(game.playedAt)) ? new Date(game.playedAt).toLocaleDateString('de-CH', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'Europe/Zurich' }) : 'Datum nicht verfügbar'} · {FORM_LABEL[game.result]} {game.score} gegen {game.opponent}</span>
                    </li>)}
                  </ol> : <p className="mt-2 text-xs text-fg-3">Keine abgeschlossenen Spiele im Archiv.</p>}
                </div>
              })}
            </div>}
            <EloChart teams={selectedTeams} history={history} matchInfo={matchInfo} />
          </GlassCard>

          <details className="overflow-hidden rounded-xl border border-line bg-surface">
            <summary className="cursor-pointer border-b border-line px-5 py-4 text-base font-medium text-fg">
              Elo-Rangliste <span className="ml-1 text-sm font-normal text-fg-2">({rows.length} Teams)</span>
            </summary>
            <div className="px-5 py-3 text-xs leading-relaxed text-fg-2">
              Sortiert nach aktuellem Elo. Δ zeigt die Veränderung seit dem ersten gespeicherten Wert. S = Siege, U = Unentschieden, N = Niederlagen. Letzte Spiele sind nach Anstoßdatum sortiert.
              {competition === 'wc2026' && ' Für USA, Kanada und Mexiko enthält das WM-Modell +80 Elo Gastgeberbonus.'}
            </div>
            <div role="list" aria-label="Power-Rangliste der Teams" className="grid gap-2 p-3 sm:hidden">
              {rows.map((row, index) => {
                const active = selectedTeams.includes(row.team)
                return <article key={row.team} role="listitem" className={cn('min-w-0 rounded-lg border border-line p-3', active && 'bg-surface-2')}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2 text-sm font-medium text-fg"><span className="w-6 shrink-0 text-right tabular-nums text-fg-3">{index + 1}</span><TeamLogo name={row.team} /><span className="truncate">{row.team}</span></div>
                    <button type="button" aria-pressed={active} disabled={!active && selectedTeams.length >= 4} onClick={() => toggleTeam(row.team)} className="min-h-11 shrink-0 rounded-lg border border-line-2 px-3 text-xs font-semibold text-fg disabled:opacity-50">{active ? 'Entfernen' : 'Vergleichen'}</button>
                  </div>
                  <div className="mt-2 flex flex-wrap items-baseline justify-between gap-2 text-xs text-fg-2">
                    <span><b className="text-base tabular-nums text-fg">{Math.round(row.elo)}</b> Elo{row.delta != null && <> · Δ {row.delta > 0 ? '+' : ''}{Math.round(row.delta)}</>}</span>
                    <span>S-U-N {row.w}-{row.d}-{row.l}</span>
                  </div>
                  <div className="mt-2 flex items-center justify-between gap-2">
                    <span className="text-[10px] text-fg-3">Letzte Resultate</span>
                    <span className="flex gap-1" aria-label={`${row.team}: ${row.last5.map((result) => FORM_LABEL[result]).join(', ') || 'keine Resultate'}`}>
                      {row.last5.map((result, resultIndex) => <span key={`${row.team}-${resultIndex}`} aria-hidden="true" className={cn('flex h-6 min-w-6 items-center justify-center rounded px-1 text-[10px] font-semibold', FORM_STYLE[result])}>{result === 'W' ? 'S' : result === 'D' ? 'U' : 'N'}</span>)}
                    </span>
                  </div>
                </article>
              })}
            </div>
            <div className="hidden min-w-0 overflow-x-auto sm:block" role="region" aria-label="Power-Rangliste der Teams" tabIndex={0}>
              <table className="w-full min-w-[620px] text-sm">
                <thead><tr className="border-y border-line bg-surface-2 text-xs font-medium text-fg-2">
                  <th scope="col" className="px-5 py-3 text-left">Rang</th><th scope="col" className="px-3 py-3 text-left">Team</th><th scope="col" className="px-3 py-3 text-right">Elo</th><th scope="col" className="px-3 py-3 text-right">Δ Elo</th><th scope="col" className="px-3 py-3 text-center max-sm:hidden">S-U-N</th><th scope="col" className="px-5 py-3 text-right">Letzte Spiele</th>
                </tr></thead>
                <tbody>{rows.map((row, index) => {
                  const active = selectedTeams.includes(row.team)
                  return <tr key={row.team} className={cn('border-b border-line last:border-0', active && 'bg-surface-2')}>
                    <td className="px-5 py-3 tabular-nums text-fg-2">{index + 1}</td>
                    <th scope="row" className="px-3 py-3 text-left font-medium text-fg"><button type="button" aria-pressed={active} disabled={!active && selectedTeams.length >= 4} onClick={() => toggleTeam(row.team)} className="inline-flex min-h-11 items-center gap-2 rounded px-1 text-left hover:text-[var(--blue)] disabled:cursor-not-allowed disabled:opacity-50"><TeamLogo name={row.team} />{row.team}</button></th>
                    <td className="px-3 py-3 text-right tabular-nums text-fg">{Math.round(row.elo)}</td>
                    <td className={cn('px-3 py-3 text-right tabular-nums', row.delta == null ? 'text-fg-3' : row.delta > 0 ? 'text-emerald-a' : row.delta < 0 ? 'text-red-a' : 'text-fg-2')}>{row.delta == null ? '–' : `${row.delta > 0 ? '+' : ''}${Math.round(row.delta)}`}</td>
                    <td className="px-3 py-3 text-center tabular-nums text-fg-2 max-sm:hidden">{row.w}-{row.d}-{row.l}</td>
                    <td className="px-5 py-3"><span className="flex justify-end gap-1" aria-label={`${row.team}: ${row.last5.map((result) => FORM_LABEL[result]).join(', ') || 'keine Resultate'}`}>
                      {row.last5.map((result, index) => <span key={`${row.team}-${index}`} aria-hidden="true" className={cn('flex h-6 min-w-6 items-center justify-center rounded px-1 text-[10px] font-semibold', FORM_STYLE[result])}>{result === 'W' ? 'S' : result === 'D' ? 'U' : 'N'}</span>)}
                    </span></td>
                  </tr>
                })}</tbody>
              </table>
            </div>
          </details>
        </>}
      </div>
    </PageTransition>
  )
}
