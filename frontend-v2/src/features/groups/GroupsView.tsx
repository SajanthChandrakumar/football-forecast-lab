import { useMemo } from 'react'
import { useArchive, useStandings } from '../../hooks/queries'
import { useAppState } from '../../state/AppState'
import { GlassCard } from '../../components/shared/GlassCard'
import { TeamLogo } from '../../components/shared/Badges'
import type { StandingsRow } from '../../lib/types'
import { validUclStandingsRows } from '../../lib/standings.mjs'
import { PageTransition, PageHeader } from '../../components/shared/PageTransition'
import { CardGridSkeleton } from '../../components/shared/Skeleton'
import { QueryState } from '../../components/shared/QueryState'

const WC_GROUPS: Record<string, string[]> = {
  A: ['Mexico', 'South Africa', 'South Korea', 'Czechia'],
  B: ['Canada', 'Bosnia and Herzegovina', 'Qatar', 'Switzerland'],
  C: ['Brazil', 'Morocco', 'Haiti', 'Scotland'],
  D: ['USA', 'Paraguay', 'Australia', 'Türkiye'],
  E: ['Germany', 'Curaçao', 'Ivory Coast', 'Ecuador'],
  F: ['Netherlands', 'Japan', 'Sweden', 'Tunisia'],
  G: ['Belgium', 'Egypt', 'Iran', 'New Zealand'],
  H: ['Spain', 'Cape Verde', 'Saudi Arabia', 'Uruguay'],
  I: ['France', 'Senegal', 'Iraq', 'Norway'],
  J: ['Argentina', 'Algeria', 'Austria', 'Jordan'],
  K: ['Portugal', 'DR Congo', 'Uzbekistan', 'Colombia'],
  L: ['England', 'Croatia', 'Ghana', 'Panama'],
}

const NORMALIZE: Record<string, string> = {
  'United States': 'USA', USA: 'USA',
  'Korea Republic': 'South Korea', 'South Korea': 'South Korea',
  'IR Iran': 'Iran', "Côte d'Ivoire": 'Ivory Coast', 'Ivory Coast': 'Ivory Coast',
  Turkey: 'Türkiye', Türkiye: 'Türkiye',
  'Bosnia & Herzegovina': 'Bosnia and Herzegovina',
  'Czech Republic': 'Czechia', Czechia: 'Czechia',
  Curacao: 'Curaçao',
}

interface Row {
  team: string
  p: number; w: number; d: number; l: number
  gf: number; ga: number
}

export function GroupsView() {
  const archiveQuery = useArchive()
  const standingsQuery = useStandings()
  const { competition } = useAppState()
  const { data: archive, isLoading: archiveLoading } = archiveQuery
  const { data: standingsData, isLoading: standingsLoading } = standingsQuery

  const standings = useMemo(() => {
    const rows = new Map<string, Row>()
    for (const teams of Object.values(WC_GROUPS)) {
      for (const team of teams) rows.set(team, { team, p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0 })
    }
    for (const match of Object.values(archive ?? {})) {
      const result = match.post_match_result
      if (result?.status !== 'completed' || !result.actual_score || match.metadata?.is_ko_phase) continue
      const [homeGoals, awayGoals] = result.actual_score.split(':').map(Number)
      if (Number.isNaN(homeGoals) || Number.isNaN(awayGoals)) continue
      const home = rows.get(normalizeTeam(match.metadata.home_team))
      const away = rows.get(normalizeTeam(match.metadata.away_team))
      if (!home || !away) continue
      home.p++; away.p++
      home.gf += homeGoals; home.ga += awayGoals
      away.gf += awayGoals; away.ga += homeGoals
      if (homeGoals > awayGoals) { home.w++; away.l++ }
      else if (awayGoals > homeGoals) { away.w++; home.l++ }
      else { home.d++; away.d++ }
    }
    return rows
  }, [archive])

  const sortRows = (teams: string[]) => teams.map((team) => standings.get(team)!).sort((a, b) => {
    const pointsDifference = (b.w * 3 + b.d) - (a.w * 3 + a.d)
    if (pointsDifference) return pointsDifference
    const goalDifference = (b.gf - b.ga) - (a.gf - a.ga)
    if (goalDifference) return goalDifference
    return b.gf - a.gf
  })

  if (competition === 'ucl2026') {
    const rows = validUclStandingsRows(standingsData?.flatMap((group) => group.rows ?? []) ?? [])
    return <UclStandings rows={rows ?? []} valid={Boolean(rows)} isLoading={standingsLoading} error={standingsQuery.error} onRetry={() => void standingsQuery.refetch()} />
  }

  if (competition !== 'wc2026') {
    return <PageTransition><PageHeader title="Tabelle" subtitle="Tabellen für diesen Wettbewerb." /><p className="text-sm text-fg-2">Für diesen Wettbewerb ist noch keine Tabellenansicht eingerichtet.</p></PageTransition>
  }

  return (
    <PageTransition>
      <PageHeader title="Gruppen" subtitle="Berechnet aus den im Archiv gespeicherten abgeschlossenen Gruppenspielen." />
      <p className="mb-4 text-xs leading-relaxed text-fg-2">Sp. = Spiele · S = Siege · U = Unentschieden · N = Niederlagen · Tore = geschossen:erhalten · TD = Tordifferenz · Pkt = Punkte</p>
      {archiveLoading && <CardGridSkeleton count={6} cols="md:grid-cols-2 xl:grid-cols-3" />}
      {!archiveLoading && archiveQuery.error && <QueryState title="Gruppendaten konnten nicht geladen werden" message="Die gespeicherten Spielergebnisse sind derzeit nicht erreichbar." onRetry={() => void archiveQuery.refetch()} />}

      {!archiveLoading && !archiveQuery.error && <div className="grid min-w-0 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {Object.entries(WC_GROUPS).map(([group, teams]) => <GlassCard key={group} className="min-w-0 !p-4">
          <h2 className="mb-1 text-base font-medium text-fg">Gruppe {group}</h2>
          <div className="min-w-0 overflow-x-auto rounded-lg border border-line" role="region" aria-label={`Tabelle Gruppe ${group}`} tabIndex={0}>
            <table className="w-full min-w-[440px] text-sm">
              <caption className="sr-only">Gruppe {group}: Spiele, Siege, Unentschieden, Niederlagen, Tore, Tordifferenz und Punkte</caption>
              <thead><tr className="border-b border-line bg-surface-2 text-xs font-medium text-fg-2">
                <th scope="col" className="px-3 py-2.5 text-left">Team</th><th scope="col" className="px-2 py-2.5 text-right">Sp.</th><th scope="col" className="px-2 py-2.5 text-right">S</th><th scope="col" className="px-2 py-2.5 text-right">U</th><th scope="col" className="px-2 py-2.5 text-right">N</th><th scope="col" className="px-2 py-2.5 text-right">Tore</th><th scope="col" className="px-2 py-2.5 text-right">TD</th><th scope="col" className="px-3 py-2.5 text-right">Pkt</th>
              </tr></thead>
              <tbody>{sortRows(teams).map((row) => <tr key={row.team} className="border-t border-line">
                <th scope="row" className="whitespace-nowrap px-3 py-2.5 text-left font-medium text-fg"><span className="inline-flex items-center gap-2"><TeamLogo name={row.team} />{row.team}</span></th>
                <td className="px-2 py-2.5 text-right tabular-nums text-fg-2">{row.p}</td><td className="px-2 py-2.5 text-right tabular-nums text-fg-2">{row.w}</td><td className="px-2 py-2.5 text-right tabular-nums text-fg-2">{row.d}</td><td className="px-2 py-2.5 text-right tabular-nums text-fg-2">{row.l}</td>
                <td className="px-2 py-2.5 text-right tabular-nums text-fg-2">{row.gf}:{row.ga}</td><td className="px-2 py-2.5 text-right tabular-nums text-fg-2">{row.gf - row.ga > 0 ? '+' : ''}{row.gf - row.ga}</td><td className="px-3 py-2.5 text-right font-medium tabular-nums text-fg">{row.w * 3 + row.d}</td>
              </tr>)}</tbody>
            </table>
          </div>
        </GlassCard>)}
      </div>}
    </PageTransition>
  )
}

function UclStandings({ rows, valid, isLoading, error, onRetry }: { rows: StandingsRow[]; valid: boolean; isLoading: boolean; error: unknown; onRetry: () => void }) {
  const sorted = [...rows].sort((a, b) => (a.pos ?? 999) - (b.pos ?? 999))
  return (
    <PageTransition>
      <PageHeader title="Ligatabelle" subtitle="Die Ligaphase mit Spielen, Torverhältnis und Punkten aller Teams." />
      {isLoading && <p className="text-sm text-fg-2">Ligatabelle wird geladen…</p>}
      {!isLoading && Boolean(error) && <QueryState title="Ligatabelle konnte nicht geladen werden" message="Die Tabelle ist derzeit nicht erreichbar." onRetry={onRetry} />}
      {!isLoading && !error && !valid && <p className="rounded-xl border border-line bg-surface px-5 py-6 text-sm text-fg-2">Die Ligatabelle ist derzeit nicht vollständig verfügbar.</p>}
      {!isLoading && !error && valid && <GlassCard className="!p-0">
        <p className="border-b border-line px-5 py-3 text-xs leading-relaxed text-fg-2">Sp. Spiele · S Siege · U Unentschieden · N Niederlagen · TD Tordifferenz · Pkt Punkte</p>
        <div className="min-w-0 overflow-x-auto" role="region" aria-label="UCL-Ligatabelle" tabIndex={0}>
          <table className="w-full min-w-[600px] text-sm">
            <thead><tr className="text-xs font-medium text-fg-2"><th scope="col" className="px-5 py-3 text-left">Pl.</th><th scope="col" className="px-3 py-3 text-left">Team</th><th scope="col" className="px-3 py-3 text-right">Sp.</th><th scope="col" className="px-3 py-3 text-right">S</th><th scope="col" className="px-3 py-3 text-right">U</th><th scope="col" className="px-3 py-3 text-right">N</th><th scope="col" className="px-3 py-3 text-right">TD</th><th scope="col" className="px-5 py-3 text-right">Pkt</th></tr></thead>
            <tbody>{sorted.map((row, index) => <tr key={row.team} className="border-t border-line">
              <td className="px-5 py-3 tabular-nums text-fg-2">{row.pos ?? index + 1}</td><th scope="row" className="px-3 py-3 text-left font-medium text-fg"><span className="inline-flex items-center gap-2"><TeamLogo name={row.team} src={row.logo} />{row.team}</span></th>
              <td className="px-3 py-3 text-right tabular-nums text-fg-2">{row.p ?? '–'}</td><td className="px-3 py-3 text-right tabular-nums text-fg-2">{row.w ?? '–'}</td><td className="px-3 py-3 text-right tabular-nums text-fg-2">{row.d ?? '–'}</td><td className="px-3 py-3 text-right tabular-nums text-fg-2">{row.l ?? '–'}</td><td className="px-3 py-3 text-right tabular-nums text-fg-2">{row.gd ?? '–'}</td><td className="px-5 py-3 text-right font-medium tabular-nums text-fg">{row.pts ?? '–'}</td>
            </tr>)}</tbody>
          </table>
        </div>
      </GlassCard>}
    </PageTransition>
  )
}

function normalizeTeam(team: string) {
  return NORMALIZE[team] ?? team
}
