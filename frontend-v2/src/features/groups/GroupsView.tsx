import { useMemo } from 'react'
import { motion } from 'framer-motion'
import { useArchive, useStandings } from '../../hooks/queries'
import { useAppState } from '../../state/AppState'
import { cn } from '../../lib/util'
import { GlassCard } from '../../components/shared/GlassCard'
import { TeamLogo } from '../../components/shared/Badges'
import type { StandingsRow } from '../../lib/types'
import { validPremierLeagueStandingsRows, validUclStandingsRows } from '../../lib/standings.mjs'
import { PageTransition, PageHeader, staggerContainer, staggerItem } from '../../components/shared/PageTransition'
import { CardGridSkeleton } from '../../components/shared/Skeleton'

// 48 teams in 12 groups — standings computed live from archive results.
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

// Groups view uses its own normalization target names (matches WC_GROUPS keys).
const NORMALIZE: Record<string, string> = {
  'United States': 'USA', USA: 'USA',
  'Korea Republic': 'South Korea', 'South Korea': 'South Korea',
  'IR Iran': 'Iran', "Côte d'Ivoire": 'Ivory Coast', 'Ivory Coast': 'Ivory Coast',
  Turkey: 'Türkiye', Türkiye: 'Türkiye',
  'Bosnia & Herzegovina': 'Bosnia and Herzegovina',
  'Czech Republic': 'Czechia', Czechia: 'Czechia',
  Curacao: 'Curaçao',
}
const norm = (t: string) => NORMALIZE[t] ?? t

interface Row {
  team: string
  p: number; w: number; d: number; l: number
  gf: number; ga: number
}

export function GroupsView() {
  const { data: archive, isLoading } = useArchive()
  const { data: standingsData, isLoading: standingsLoading } = useStandings()
  const { competition } = useAppState()

  const standings = useMemo(() => {
    const rows = new Map<string, Row>()
    for (const teams of Object.values(WC_GROUPS)) {
      for (const t of teams) rows.set(t, { team: t, p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0 })
    }
    for (const m of Object.values(archive ?? {})) {
      const pmr = m.post_match_result
      if (pmr?.status !== 'completed' || !pmr.actual_score || m.metadata?.is_ko_phase) continue
      const [hs, as] = pmr.actual_score.split(':').map(Number)
      if (Number.isNaN(hs) || Number.isNaN(as)) continue
      const home = rows.get(norm(m.metadata.home_team))
      const away = rows.get(norm(m.metadata.away_team))
      if (!home || !away) continue
      home.p++; away.p++
      home.gf += hs; home.ga += as
      away.gf += as; away.ga += hs
      if (hs > as) { home.w++; away.l++ }
      else if (as > hs) { away.w++; home.l++ }
      else { home.d++; away.d++ }
    }
    return rows
  }, [archive])

  const sortRows = (teams: string[]) =>
    teams
      .map((t) => standings.get(t)!)
      .sort((a, b) => {
        const pa = a.w * 3 + a.d
        const pb = b.w * 3 + b.d
        if (pb !== pa) return pb - pa
        const gda = a.gf - a.ga
        const gdb = b.gf - b.ga
        if (gdb !== gda) return gdb - gda
        return b.gf - a.gf
      })

  if (competition === 'ucl2026') {
    const officialRows = standingsData?.flatMap((group) => group.rows ?? []) ?? []
    const rows = validUclStandingsRows(officialRows)
    return <UclStandings rows={rows ?? []} valid={Boolean(rows)} isLoading={standingsLoading} />
  }

  if (competition === 'epl2026') {
    const officialRows = standingsData?.flatMap((group) => group.rows ?? []) ?? []
    const rows = validPremierLeagueStandingsRows(officialRows)
    return <PremierLeagueStandings rows={rows ?? []} valid={Boolean(rows)} isLoading={standingsLoading} />
  }

  if (competition !== 'wc2026') {
    return <PageTransition><PageHeader title="Tabelle" subtitle="Tabellen für diesen Wettbewerb." /><p className="text-sm text-fg-2">Für diesen Wettbewerb ist noch keine Tabellenansicht eingerichtet.</p></PageTransition>
  }

  return (
    <PageTransition>
      <PageHeader title="Gruppen" subtitle="Tabellen aus den bisherigen Resultaten — Top 2 qualifiziert, Platz 3 mit Playoff-Chance." />
      {isLoading && <CardGridSkeleton count={6} cols="md:grid-cols-2 xl:grid-cols-3" />}

      <motion.div
        variants={staggerContainer} initial="initial" animate="animate"
        className={cn('grid gap-4 md:grid-cols-2 xl:grid-cols-3', isLoading && 'hidden')}
      >
        {Object.entries(WC_GROUPS).map(([group, teams]) => (
          <motion.div key={group} variants={staggerItem}>
            <GlassCard className="!p-4">
              <h3 className="mb-2 font-display text-xl font-extrabold text-emerald-a">Gruppe {group}</h3>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[10px] font-bold uppercase tracking-wider text-fg-3">
                    <th className="pb-1 text-left">Team</th>
                    <th className="pb-1 text-right">P</th>
                    <th className="pb-1 text-right">S</th>
                    <th className="pb-1 text-right">U</th>
                    <th className="pb-1 text-right">N</th>
                    <th className="pb-1 text-right max-sm:hidden">Tore</th>
                    <th className="pb-1 text-right">TD</th>
                    <th className="pb-1 text-right">Pkt</th>
                  </tr>
                </thead>
                <tbody>
                  {sortRows(teams).map((r, i) => (
                    <tr
                      key={r.team}
                      className={cn(
                        'border-t border-line',
                        i < 2 && 'bg-emerald-dim/40',
                        i === 2 && 'bg-amber-a/5',
                        i > 2 && 'opacity-60',
                      )}
                    >
                      <td className="py-1.5 font-semibold text-fg">
                        <span className="inline-flex items-center gap-1.5"><TeamLogo name={r.team} />{r.team}</span>
                      </td>
                      <td className="py-1.5 text-right tabular-nums text-fg-2">{r.p}</td>
                      <td className="py-1.5 text-right tabular-nums text-fg-2">{r.w}</td>
                      <td className="py-1.5 text-right tabular-nums text-fg-2">{r.d}</td>
                      <td className="py-1.5 text-right tabular-nums text-fg-2">{r.l}</td>
                      <td className="py-1.5 text-right tabular-nums text-fg-2 max-sm:hidden">{r.gf}:{r.ga}</td>
                      <td className="py-1.5 text-right tabular-nums text-fg-2">{r.gf - r.ga > 0 ? '+' : ''}{r.gf - r.ga}</td>
                      <td className="display-num py-1.5 text-right text-fg">{r.w * 3 + r.d}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </GlassCard>
          </motion.div>
        ))}
      </motion.div>
    </PageTransition>
  )
}

function PremierLeagueStandings({ rows, valid, isLoading }: { rows: StandingsRow[]; valid: boolean; isLoading: boolean }) {
  return (
    <PageTransition>
      <PageHeader title="Premier League 2026/27" subtitle="Ligatabelle · 20 Clubs." />
      {isLoading && <p className="text-fg-2">Ligatabelle wird geladen…</p>}
      {!isLoading && !valid && <p className="text-fg-2">Die vollständige Premier-League-Tabelle mit 20 Clubs ist derzeit nicht verfügbar.</p>}
      {valid && <GlassCard className="!p-0 overflow-hidden">
        <p className="border-b border-line px-5 py-3 text-xs text-fg-2">P Spiele · S Siege · U Unentschieden · N Niederlagen · TD Tordifferenz · Pkt Punkte</p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-[10px] font-bold uppercase tracking-wider text-fg-3">
              <th className="px-5 py-2">#</th><th className="px-2 py-2">Club</th><th className="px-2 py-2 text-right">P</th><th className="px-2 py-2 text-right">S</th><th className="px-2 py-2 text-right">U</th><th className="px-2 py-2 text-right">N</th><th className="px-2 py-2 text-right max-sm:hidden">Tore</th><th className="px-2 py-2 text-right">TD</th><th className="px-5 py-2 text-right">Pkt</th>
            </tr></thead>
            <tbody>{rows.map((row, index) => <tr key={row.team} className="border-t border-line">
              <td className="px-5 py-2 tabular-nums text-fg-3">{row.pos ?? index + 1}</td>
              <td className="px-2 py-2 font-semibold text-fg"><TeamLogo name={row.team} src={row.logo} /> <span className="ml-1">{row.team}</span></td>
              <td className="px-2 py-2 text-right tabular-nums text-fg-2">{row.p ?? '–'}</td>
              <td className="px-2 py-2 text-right tabular-nums text-fg-2">{row.w ?? '–'}</td>
              <td className="px-2 py-2 text-right tabular-nums text-fg-2">{row.d ?? '–'}</td>
              <td className="px-2 py-2 text-right tabular-nums text-fg-2">{row.l ?? '–'}</td>
              <td className="px-2 py-2 text-right tabular-nums text-fg-2 max-sm:hidden">{row.gf != null && row.ga != null ? `${row.gf}:${row.ga}` : '–'}</td>
              <td className="px-2 py-2 text-right tabular-nums text-fg-2">{row.gd ?? '–'}</td>
              <td className="display-num px-5 py-2 text-right text-fg">{row.pts ?? '–'}</td>
            </tr>)}</tbody>
          </table>
        </div>
      </GlassCard>}
    </PageTransition>
  )
}

function UclStandings({ rows, valid, isLoading }: { rows: StandingsRow[]; valid: boolean; isLoading: boolean }) {
  const sorted = [...rows].sort((a, b) => (a.pos ?? 999) - (b.pos ?? 999))
  return (
    <PageTransition>
      <PageHeader title="Ligatabelle" subtitle="Die aktuelle Ligaphase mit Spielen, Torverhältnis und Punkten aller 36 Teams." />
      {isLoading && <p className="text-fg-2">Ligatabelle wird geladen…</p>}
      {!isLoading && !valid && <p className="text-fg-2">Die offizielle Ligatabelle ist derzeit nicht vollständig verfügbar.</p>}
      {valid && <GlassCard className="!p-0 overflow-hidden">
        <p className="border-b border-line px-5 py-3 text-xs text-fg-2">P Spiele · S Siege · U Unentschieden · N Niederlagen · TD Tordifferenz · Pkt Punkte</p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-[10px] font-bold uppercase tracking-wider text-fg-3">
              <th className="px-5 py-2">#</th><th className="px-2 py-2">Team</th><th className="px-2 py-2 text-right">P</th><th className="px-2 py-2 text-right">S</th><th className="px-2 py-2 text-right">U</th><th className="px-2 py-2 text-right">N</th><th className="px-2 py-2 text-right">TD</th><th className="px-5 py-2 text-right">Pkt</th>
            </tr></thead>
            <tbody>{sorted.map((row, index) => {
              const pos = row.pos ?? index + 1
              return <tr key={row.team} className={cn('border-t border-line', pos <= 8 && 'bg-emerald-dim/40', pos > 24 && 'opacity-60')}>
                <td className="px-5 py-2 tabular-nums text-fg-3">{pos}</td>
                <td className="px-2 py-2 font-semibold text-fg"><TeamLogo name={row.team} src={row.logo} /> <span className="ml-1">{row.team}</span></td>
                <td className="px-2 py-2 text-right tabular-nums text-fg-2">{row.p ?? '–'}</td>
                <td className="px-2 py-2 text-right tabular-nums text-fg-2">{row.w ?? '–'}</td>
                <td className="px-2 py-2 text-right tabular-nums text-fg-2">{row.d ?? '–'}</td>
                <td className="px-2 py-2 text-right tabular-nums text-fg-2">{row.l ?? '–'}</td>
                <td className="px-2 py-2 text-right tabular-nums text-fg-2">{row.gd ?? '–'}</td>
                <td className="display-num px-5 py-2 text-right text-fg">{row.pts ?? '–'}</td>
              </tr>
            })}</tbody>
          </table>
        </div>
      </GlassCard>}
    </PageTransition>
  )
}
