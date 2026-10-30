import { useMemo, type ReactNode } from 'react'
import { useMatch } from 'react-router-dom'
import { useMatchCore, useMatches, useStandings } from '../../hooks/queries'
import { collectTeamLogos } from '../../lib/team-visuals.mjs'
import { TeamLogos } from './TeamVisualsContext'
import { useAppState } from '../../state/AppState'

export function TeamVisualsProvider({ children }: { children: ReactNode }) {
  const dataPage = useMatch('/data-sources')
  const homePage = useMatch('/')
  const detailPage = useMatch('/match/:id')
  const { competition } = useAppState()
  if (dataPage) return <>{children}</>
  if (detailPage && competition !== 'wc2026') return <ClubMatchTeamVisuals matchId={detailPage.params.id!}>{children}</ClubMatchTeamVisuals>
  return <FootballTeamVisuals overview={Boolean(homePage)}>{children}</FootballTeamVisuals>
}

function FootballTeamVisuals({ children, overview }: { children: ReactNode; overview: boolean }) {
  const { data: matches } = useMatches(overview, !overview)
  const { data: standings } = useStandings()
  const logos = useMemo(() => collectTeamLogos(matches, standings), [matches, standings])
  return <TeamLogos.Provider value={logos}>{children}</TeamLogos.Provider>
}

function ClubMatchTeamVisuals({ children, matchId }: { children: ReactNode; matchId: string }) {
  const { data: match } = useMatchCore(matchId, false)
  const logos = useMemo(() => collectTeamLogos(match ? [match] : [], []), [match])
  return <TeamLogos.Provider value={logos}>{children}</TeamLogos.Provider>
}
