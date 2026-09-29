import { useMemo, type ReactNode } from 'react'
import { useMatches, useStandings } from '../../hooks/queries'
import { collectTeamLogos } from '../../lib/team-visuals.mjs'
import { TeamLogos } from './TeamVisualsContext'

export function TeamVisualsProvider({ children }: { children: ReactNode }) {
  const { data: matches } = useMatches()
  const { data: standings } = useStandings()
  const logos = useMemo(() => collectTeamLogos(matches, standings), [matches, standings])
  return <TeamLogos.Provider value={logos}>{children}</TeamLogos.Provider>
}
