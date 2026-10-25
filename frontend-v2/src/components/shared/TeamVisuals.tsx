import { useMemo, type ReactNode } from 'react'
import { useMatch } from 'react-router-dom'
import { useMatches, useStandings } from '../../hooks/queries'
import { collectTeamLogos } from '../../lib/team-visuals.mjs'
import { TeamLogos } from './TeamVisualsContext'

export function TeamVisualsProvider({ children }: { children: ReactNode }) {
  const dataPage = useMatch('/data-sources')
  const homePage = useMatch('/')
  return dataPage ? <>{children}</> : <FootballTeamVisuals overview={Boolean(homePage)}>{children}</FootballTeamVisuals>
}

function FootballTeamVisuals({ children, overview }: { children: ReactNode; overview: boolean }) {
  const { data: matches } = useMatches(overview)
  const { data: standings } = useStandings()
  const logos = useMemo(() => collectTeamLogos(matches, standings), [matches, standings])
  return <TeamLogos.Provider value={logos}>{children}</TeamLogos.Provider>
}
