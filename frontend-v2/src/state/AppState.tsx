import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { validCompetition } from '../lib/competition.mjs'
import { readTeamSelection, sanitizeTeamSelection, writeTeamSelection } from '../lib/team-selection.mjs'
import type { CompetitionId, CompetitionInfo } from '../lib/types'

interface AppState {
  competition: CompetitionId
  setCompetition: (value: CompetitionId) => void
  competitions: CompetitionInfo[]
  competitionsLoading: boolean
  light: boolean
  toggleTheme: () => void
  selectedTeams: string[] | null
  setSelectedTeams: (teams: string[]) => void
  toggleTeam: (team: string) => void
}

const Ctx = createContext<AppState | null>(null)
const MAX_TEAMS = 4
const STORAGE_KEY = 'competition'

export function AppStateProvider({
  children, light, toggleTheme,
}: { children: ReactNode; light: boolean; toggleTheme: () => void }) {
  const storedCompetition = useRef<string | null>(null)
  const [competition, setCompetitionState] = useState<CompetitionId>(() => {
    try {
      storedCompetition.current = localStorage.getItem(STORAGE_KEY)
      return validCompetition(storedCompetition.current)
    }
    catch { return 'ucl2026' }
  })
  const [selectedTeamsByCompetition, setSelectedTeamsByCompetition] = useState<Record<CompetitionId, string[] | null>>(() => ({
    wc2026: readTeamSelection('wc2026'),
    ucl2026: readTeamSelection('ucl2026'),
  }))
  const { data: competitions = [], isLoading: competitionsLoading } = useQuery({
    queryKey: ['competitions'],
    queryFn: api.competitions,
    staleTime: 86_400_000,
  })

  useEffect(() => {
    if (!competitions.length || !storedCompetition.current) return
    setCompetitionState(validCompetition(storedCompetition.current, competitions.map((item) => item.id)))
    storedCompetition.current = null
  }, [competitions])

  useEffect(() => { localStorage.setItem(STORAGE_KEY, competition) }, [competition])
  useEffect(() => {
    for (const [id, teams] of Object.entries(selectedTeamsByCompetition)) {
      if (teams !== null) writeTeamSelection(id, teams)
    }
  }, [selectedTeamsByCompetition])

  const setCompetition = useCallback((value: CompetitionId) => {
    storedCompetition.current = null
    setCompetitionState(validCompetition(value, competitions.length ? competitions.map((item) => item.id) : undefined))
  }, [competitions])

  const setSelectedTeams = useCallback((teams: string[]) => {
    setSelectedTeamsByCompetition((state) => ({
      ...state,
      [competition]: sanitizeTeamSelection(teams),
    }))
  }, [competition])

  // FIFO eviction when a 5th team is selected (legacy behavior).
  const toggleTeam = useCallback((team: string) => {
    setSelectedTeamsByCompetition((state) => {
      const prev = state[competition] ?? []
      return {
        ...state,
        [competition]: prev.includes(team)
          ? prev.filter((t) => t !== team)
          : sanitizeTeamSelection([...prev.slice(prev.length >= MAX_TEAMS ? 1 : 0), team]),
      }
    })
  }, [competition])

  const selectedTeams = useMemo(() => selectedTeamsByCompetition[competition] ?? null, [selectedTeamsByCompetition, competition])

  const value = useMemo(
    () => ({ competition, setCompetition, competitions, competitionsLoading, light, toggleTheme, selectedTeams, setSelectedTeams, toggleTeam }),
    [competition, setCompetition, competitions, competitionsLoading, light, toggleTheme, selectedTeams, setSelectedTeams, toggleTeam],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAppState(): AppState {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useAppState must be used within AppStateProvider')
  return ctx
}
