import { useMemo, useState } from 'react'
import { useAppState } from '../../state/AppState'
import { cn } from '../../lib/util'
import { GlassCard, SectionTitle } from '../../components/shared/GlassCard'
import { TeamLogo } from '../../components/shared/Badges'
import { PageTransition, PageHeader } from '../../components/shared/PageTransition'
import { ChartSkeleton, CardGridSkeleton } from '../../components/shared/Skeleton'
import { useTeamFormData } from './useTeamFormData'
import { EloChart } from './EloChart'

const FORM_STYLE: Record<string, string> = {
  W: 'bg-emerald-dim text-emerald-a',
  D: 'bg-surface-2 text-fg-3',
  L: 'bg-red-a/10 text-red-a',
}

export function TeamFormView() {
  const { rows, history, matchInfo, coverage, isLoading } = useTeamFormData()
  const { competition, selectedTeams: storedSelectedTeams, toggleTeam } = useAppState()
  const incompleteUclRatings = competition === 'ucl2026' && !coverage.complete
  const staleUclRatings = competition === 'ucl2026' && coverage.complete && coverage.showAlert
  const incompleteEplStandings = competition === 'epl2026' && !coverage.standingsValid
  const partialEplRatings = competition === 'epl2026' && coverage.standingsValid && !coverage.complete
  const staleEplRatings = competition === 'epl2026' && coverage.complete && coverage.showAlert
  const selectedTeams = storedSelectedTeams.filter((team) => rows.some((row) => row.team === team))
  const [search, setSearch] = useState('')

  const filtered = useMemo(
    () => rows.filter((r) => r.team.toLowerCase().includes(search.toLowerCase())),
    [rows, search],
  )

  return (
    <PageTransition>
      <PageHeader title="Teamvergleich" subtitle="Stärke und Form von bis zu vier Teams vergleichen." />
      {isLoading && (
        <div className="space-y-4">
          <ChartSkeleton />
          <CardGridSkeleton count={1} cols="grid-cols-1" />
        </div>
      )}

      <div className={cn('space-y-4', isLoading && 'hidden')}>
        {incompleteUclRatings ? (
          <div role="alert" className="rounded-xl border border-amber-a/30 bg-amber-a/5 px-4 py-3 text-center text-sm text-fg-2">
            {!coverage.standingsValid ? (
              <p>Team Form nicht verfügbar: Die vollständige offizielle UCL-Tabelle fehlt.</p>
            ) : (
              <>
                <p>Team Form nicht verfügbar: ClubElo-Ratings liegen nur für {coverage.available} von {coverage.required} UCL-Teams vor.</p>
                <p className="mt-1 text-xs text-fg-3">Fehlende Teams: {coverage.missing.join(', ')}</p>
              </>
            )}
          </div>
        ) : incompleteEplStandings ? (
          <div role="alert" className="rounded-xl border border-amber-a/30 bg-amber-a/5 px-4 py-3 text-center text-sm text-fg-2">
            Teamvergleich für die Premier League nicht verfügbar: Die vollständige Tabelle mit 20 Clubs fehlt.
          </div>
        ) : partialEplRatings ? (
          <div role="alert" className="rounded-xl border border-amber-a/30 bg-amber-a/5 px-4 py-3 text-center text-sm text-fg-2">
            <p>ClubElo-Ratings sind für {coverage.available} von {coverage.required} Premier-League-Teams verfügbar.</p>
            {coverage.missing.length > 0 && <p className="mt-1 text-xs text-fg-3">Fehlende Teams: {coverage.missing.join(', ')}</p>}
          </div>
        ) : rows.length === 0 && (
          <p className="text-center text-sm text-fg-3">
            Keine Teamratings verfügbar.
          </p>
        )}
        {staleEplRatings && <p role="alert" className="rounded-xl border border-amber-a/30 bg-amber-a/5 px-4 py-3 text-sm text-fg-2">Der ClubElo-Datenstand für die Premier League ist möglicherweise veraltet. Wir zeigen die letzten gespeicherten Ratings.</p>}
        {staleUclRatings && (
          <div role="alert" className="rounded-xl border border-amber-a/30 bg-amber-a/5 px-4 py-3 text-center text-sm text-fg-2">
            <p>
              ClubElo ist aktuell nur für {coverage.snapshotAvailable} von {coverage.snapshotRequired} UCL-Teams verfügbar.
              {' '}Darum zeigen wir vorübergehend die letzten vollständigen Ratings.
            </p>
            {coverage.snapshotMissing.length > 0 && (
              <p className="mt-1 text-xs text-fg-3">Fehlende aktuelle Teams: {coverage.snapshotMissing.join(', ')}</p>
            )}
          </div>
        )}
        {!incompleteUclRatings && !incompleteEplStandings && <>
        {/* Chart + picker */}
        <GlassCard>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <SectionTitle>Teams vergleichen</SectionTitle>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Team suchen…"
              className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-fg outline-none placeholder:text-fg-3 focus:border-emerald-a/50"
            />
          </div>

          <div className="mb-4 flex max-h-24 flex-wrap gap-1.5 overflow-y-auto">
            {filtered.map((r) => {
              const active = selectedTeams.includes(r.team)
              return (
                <button
                  key={r.team}
                  type="button"
                  aria-pressed={active}
                  onClick={() => toggleTeam(r.team)}
                  className={cn(
                    'rounded-lg border px-2.5 py-1.5 text-xs font-semibold transition',
                    active
                      ? 'border-[#193b2b] bg-[#193b2b] text-white'
                      : 'border-line bg-surface text-fg-2 hover:border-line-2',
                  )}
                >
                  <span className="inline-flex items-center gap-1.5"><TeamLogo name={r.team} />{r.team}</span>
                </button>
              )
            })}
          </div>

          {selectedTeams.length > 0 && (
            <div className="mb-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {selectedTeams.map((team) => {
                const row = rows.find((item) => item.team === team)
                if (!row) return null
                return (
                  <div key={team} className="rounded-xl border border-line bg-surface-2 px-3 py-3">
                    <div className="flex items-center gap-1.5 truncate text-xs font-semibold text-fg-2"><TeamLogo name={team} /><span className="truncate">{team}</span></div>
                    <div className="mt-1 font-display text-2xl font-bold tabular-nums text-fg">{Math.round(row.elo)} <span className="text-xs font-medium text-fg-3">Elo</span></div>
                    <div className="mt-1 text-xs text-fg-2">Letzte Spiele: {row.last5.length ? row.last5.map((result) => result === 'W' ? 'S' : result === 'D' ? 'U' : 'N').join(' · ') : 'keine Resultate'}</div>
                  </div>
                )
              })}
            </div>
          )}
          <EloChart teams={selectedTeams} history={history} matchInfo={matchInfo} />
        </GlassCard>

        {/* Power rankings */}
        <GlassCard className="!p-0">
          <div className="border-b border-line px-5 py-4">
            <SectionTitle>Power Rankings</SectionTitle>
            {competition === 'wc2026' && <p className="mt-1 text-xs text-fg-3">
              Gastgeber-Bonus: +80 Elo für 🇺🇸 USA, 🇨🇦 Kanada & 🇲🇽 Mexiko · Zeile anklicken für den Chart
            </p>}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[10px] font-bold uppercase tracking-wider text-fg-3">
                  <th className="px-5 py-2">#</th>
                  <th className="px-2 py-2">Team</th>
                  <th className="px-2 py-2 text-right">Elo</th>
                  <th className="px-2 py-2 text-right">Δ</th>
                  <th className="px-2 py-2 text-center max-sm:hidden">S-U-N</th>
                  <th className="px-5 py-2 text-right">Form</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const active = selectedTeams.includes(r.team)
                  return (
                    <tr
                      key={r.team}
                      onClick={() => toggleTeam(r.team)}
                      className={cn(
                        'cursor-pointer border-t border-line transition hover:bg-surface-2',
                        active && 'bg-gold-dim/60',
                      )}
                    >
                      <td className="px-5 py-2 tabular-nums text-fg-3">{i + 1}</td>
                      <td className="px-2 py-2 font-semibold text-fg"><span className="inline-flex items-center gap-1.5"><TeamLogo name={r.team} />{r.team}</span></td>
                      <td className="display-num px-2 py-2 text-right text-fg">{Math.round(r.elo)}</td>
                      <td className={cn('px-2 py-2 text-right tabular-nums', r.delta == null ? 'text-fg-3' : r.delta > 0 ? 'text-emerald-a' : r.delta < 0 ? 'text-red-a' : 'text-fg-3')}>
                        {r.delta == null ? '–' : `${r.delta > 0 ? '+' : ''}${Math.round(r.delta)}`}
                      </td>
                      <td className="px-2 py-2 text-center tabular-nums text-fg-2 max-sm:hidden">
                        {r.w}-{r.d}-{r.l}
                      </td>
                      <td className="px-5 py-2">
                        <span className="flex justify-end gap-0.5">
                          {r.last5.map((res, j) => (
                            <span key={j} className={cn('flex h-4 w-4 items-center justify-center rounded text-[9px] font-extrabold', FORM_STYLE[res])}>
                              {res === 'W' ? 'S' : res === 'D' ? 'U' : 'N'}
                            </span>
                          ))}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </GlassCard>
        </>}
      </div>
    </PageTransition>
  )
}
