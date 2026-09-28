import { lazy, Suspense, type ComponentType } from 'react'
import { HashRouter, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { AppStateProvider } from './state/AppState'
import { useTheme } from './hooks/useTheme'
import { CardGridSkeleton } from './components/shared/Skeleton'
import { TeamVisualsProvider } from './components/shared/TeamVisuals'

// Route-level code splitting: each view (and its heavy deps like recharts)
// loads on demand instead of bloating the initial bundle.
const DashboardView = lazy(() => import('./features/dashboard/DashboardView').then((m) => ({ default: m.DashboardView })))
const DetailView = lazy(() => import('./features/detail/DetailView').then((m) => ({ default: m.DetailView })))
const ValueBetsView = lazy(() => import('./features/value-bets/ValueBetsView').then((m) => ({ default: m.ValueBetsView })))
const EdgeView = lazy(() => import('./features/edge/EdgeView').then((m) => ({ default: m.EdgeView })))
const TeamFormView = lazy(() => import('./features/team-form/TeamFormView').then((m) => ({ default: m.TeamFormView })))
const GroupsView = lazy(() => import('./features/groups/GroupsView').then((m) => ({ default: m.GroupsView })))
const PerformanceView = lazy(() => import('./features/performance/PerformanceView').then((m) => ({ default: m.PerformanceView })))
const SimulatorView = lazy(() => import('./features/simulator/SimulatorView').then((m) => ({ default: m.SimulatorView })))

const suspend = (View: ComponentType) => (
  <Suspense fallback={<CardGridSkeleton count={4} />}>
    <View />
  </Suspense>
)

export default function App() {
  const { light, toggle } = useTheme()
  return (
    <AppStateProvider light={light} toggleTheme={toggle}>
      <TeamVisualsProvider>
        <HashRouter>
          <Routes>
            <Route element={<AppShell />}>
              <Route path="/" element={suspend(DashboardView)} />
              <Route path="/match/:id" element={suspend(DetailView)} />
              <Route path="/value-bets" element={suspend(ValueBetsView)} />
              <Route path="/edge" element={suspend(EdgeView)} />
              <Route path="/team-form" element={suspend(TeamFormView)} />
              <Route path="/groups" element={suspend(GroupsView)} />
              <Route path="/performance" element={suspend(PerformanceView)} />
              <Route path="/simulator" element={suspend(SimulatorView)} />
            </Route>
          </Routes>
        </HashRouter>
      </TeamVisualsProvider>
    </AppStateProvider>
  )
}
