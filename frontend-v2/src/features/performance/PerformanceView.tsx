import { useEffect, useState } from 'react'
import { useAppState } from '../../state/AppState'
import { SavedTips } from './SavedTips'
import { GlassCard, SectionTitle } from '../../components/shared/GlassCard'
import { PageTransition, PageHeader } from '../../components/shared/PageTransition'
import { PerformanceSkeleton } from '../../components/shared/Skeleton'
import { QueryState } from '../../components/shared/QueryState'
import { usePerformanceData } from './usePerformanceData'
import { BotScoreboard } from './BotScoreboard'
import { PointsRaceChart } from './PointsRaceChart'
import { BuildABot } from './BuildABot'
import { MatchHistory } from './MatchHistory'
import { ModelComparison } from './ModelComparison'
import { ForecastEvaluation } from './ForecastEvaluation'
import { ViewTabs, ViewPanel } from '../../components/shared/ViewTabs'
import { useView } from '../../hooks/useView'

const PERFORMANCE_VIEWS = ['tips', 'points', 'comparison', 'bots'] as const

const PERFORMANCE_TABS = [
  { value: 'tips', label: 'Gespeicherte Tipps' },
  { value: 'points', label: 'Punkte & Verlauf' },
  { value: 'comparison', label: 'Modellvergleich' },
  { value: 'bots', label: 'Bots & Rücktests' },
] as const

export function PerformanceView() {
  const { competition } = useAppState()
  const [view, setView] = useView(PERFORMANCE_VIEWS, 'tips')
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const clock = window.setInterval(() => setNow(Date.now()), 15_000)
    return () => window.clearInterval(clock)
  }, [])
  const {
    archive, completed, totals, botStats, comparison, extraBots, customBot, simulate,
    isLoading, isError, retryArchive,
  } = usePerformanceData()

  const commonTipRate = totals.userCount > 0 ? `${((totals.userCount / Math.max(totals.completed, 1)) * 100).toFixed(0)}%` : '—'
  const sharedPointsPerGame = comparison.matches > 0 ? formatAverage(comparison.userPoints, comparison.matches) : '—'
  const modelPointsPerGame = comparison.matches > 0 ? formatAverage(comparison.algoPoints, comparison.matches) : '—'
  const archiveUnavailable = isError && !archive

  return (
    <PageTransition>
      <PageHeader title="Tipps & Auswertung" subtitle="Gemeinsame Tipps · Punkte & Treffer" />
      <ViewTabs id="performance" label="Auswertungsansicht" items={PERFORMANCE_TABS} value={view} onChange={setView} />

      <ViewPanel id="performance" value="tips" active={view}>
        <div className="analysis-section space-y-4">
          {isLoading && !archive ? <PerformanceSkeleton /> : !archiveUnavailable && <SavedTips key={competition} archive={archive ?? {}} now={now} />}
          {archiveUnavailable && <QueryState
            title="Auswertung nicht verfügbar"
            message="Die gespeicherten Spieldaten konnten nicht geladen werden. Prüfe die Verbindung und versuche es erneut."
            onRetry={() => { void retryArchive() }}
          />}
          {isError && archive && <QueryState
            title="Aktualisierung fehlgeschlagen"
            message="Die zuletzt gespeicherte Auswertung wird angezeigt. Neue Spieldaten konnten nicht geladen werden."
            onRetry={() => { void retryArchive() }}
          />}
        </div>
      </ViewPanel>

      <ViewPanel id="performance" value="points" active={view}>
        <div className="analysis-section space-y-4">
          {isLoading && !archive ? <PerformanceSkeleton /> : archiveUnavailable ? <QueryState
            title="Punkteverlauf nicht verfügbar"
            message="Die gespeicherten Spieldaten konnten nicht geladen werden. Versuche es erneut."
            onRetry={() => { void retryArchive() }}
          /> : <>
            {isError && archive && <QueryState
              title="Aktualisierung fehlgeschlagen"
              message="Die zuletzt gespeicherte Auswertung wird angezeigt. Neue Spieldaten konnten nicht geladen werden."
              onRetry={() => { void retryArchive() }}
            />}
            <GlassCard className="surface-panel">
              <SectionTitle className="mb-4">Übersicht</SectionTitle>
              <div className="metric-strip grid grid-cols-1 gap-3 sm:grid-cols-3">
                <Kpi label="Abgeschlossene Spiele" value={String(totals.completed)} />
                <Kpi label="Gemeinsame Tipps" value={String(Object.values(archive ?? {}).filter(entry => entry.prediction?.user_tip?.trim()).length)} />
                <Kpi label="Abgeschlossene Spiele mit Tipp" value={commonTipRate} />
              </div>
              {totals.userCount > 0 && (
                <p className="mt-4 border-t border-line pt-4 text-sm text-fg-2">
                  Gesamtpunkte aus allen gespeicherten gemeinsamen Tipps: <b className="tabular-nums text-fg">{totals.totalPoints}</b>
                </p>
              )}
              {totals.completed === 0 && (
                <p className="mt-2 text-sm text-fg-2">Noch keine abgeschlossenen Spiele. Ergebnisse erscheinen hier nach der Auswertung.</p>
              )}
            </GlassCard>

            <PointsRaceChart completed={completed} extraBots={extraBots} />
            <MatchHistory completed={completed} hasReconstructed={totals.hasReconstructed} />
          </>}
        </div>
      </ViewPanel>

      <ViewPanel id="performance" value="comparison" active={view}>
        <div className="analysis-section space-y-4">
          <GlassCard className="surface-panel">
            <SectionTitle className="mb-2">Gemeinsame Tipps vs. Modell</SectionTitle>
            <details className="info-disclosure mb-3"><summary>Vergleichsgrundlage · gemeinsame Vorabspiele</summary><p className="info-content">
              Gezählt werden nur abgeschlossene Spiele mit gemeinsamem Tipp und gespeichertem Vorab-Modelltipp.
              Nachträglich rekonstruierte Elo-Tipps bleiben ausgeschlossen.
            </p></details>

            {comparison.matches > 0 ? (
              <>
                <p className="mb-4 text-sm font-semibold text-fg">
                  {comparison.matches} gemeinsame {comparison.matches === 1 ? 'Spiel' : 'Spiele'}
                </p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <ComparisonStat
                    label="Gemeinsame Tipps"
                    points={comparison.userPoints}
                    average={sharedPointsPerGame}
                    tendency={comparison.userTendency}
                    matches={comparison.matches}
                    tone="text-fg"
                  />
                  <ComparisonStat
                    label="Modell"
                    points={comparison.algoPoints}
                    average={modelPointsPerGame}
                    tendency={comparison.algoTendency}
                    matches={comparison.matches}
                    tone="text-blue-a"
                  />
                </div>
              </>
            ) : (
              <p className="rounded-lg border border-line bg-surface px-4 py-3 text-sm leading-relaxed text-fg-2">
                Für einen gemeinsamen Vergleich fehlen noch abgeschlossene Spiele mit beiden gespeicherten Tipps und ausgewerteten Punkten.
              </p>
            )}

            {totals.reconstructedCount > 0 && (
              <p className="mt-4 text-xs leading-relaxed text-fg-3">
                {totals.reconstructedCount} nachträglich aus Elo-Ratings rekonstruierte Modelltipps sind ausgeschlossen.
              </p>
            )}
          </GlassCard>

          <ForecastEvaluation />
          <ModelComparison />
          <GlassCard>
            <SectionTitle>Gesamte gespeicherte Modellhistorie</SectionTitle>
            <p className="mt-3 text-sm text-fg-2">Modell · {totals.algoAllCount} Tipps gesamt: <b className="tabular-nums text-fg">{totals.algoAllTotal}</b> Punkte.</p>
            <p className="mt-2 text-xs text-fg-3">{totals.algoCount} belegte Vorabspiele · {totals.legacyCount} ältere, nicht belegbare Tipps ({totals.legacyPoints} Punkte) · {totals.reconstructedCount} rekonstruierte Tipps ({totals.reconstructedPoints} Punkte). Diese Gesamtsumme verwendet andere Spiele als der faire Vergleich.</p>
          </GlassCard>
        </div>
      </ViewPanel>

      <ViewPanel id="performance" value="bots" active={view}>
        <div className="analysis-section space-y-4">
          <BotScoreboard totals={totals} botStats={botStats} extraBots={extraBots} />
          <BuildABot
            customBot={customBot}
            simulate={simulate}
            completed={completed}
            commonMatchIds={comparison.matchIds}
          />
          <PointsRaceChart completed={completed} commonMatchIds={comparison.matchIds} />
        </div>
      </ViewPanel>
    </PageTransition>
  )
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-lg border border-line px-4 py-4">
      <div className="text-sm font-medium text-fg-2">{label}</div>
      <div className="mt-2 font-display text-3xl font-bold leading-none tabular-nums text-fg sm:text-4xl">{value}</div>
    </div>
  )
}

function ComparisonStat({ label, points, average, tendency, matches, tone }: {
  label: string
  points: number
  average: string
  tendency: number
  matches: number
  tone: string
}) {
  const hitRate = `${((tendency / matches) * 100).toFixed(0)}%`
  return (
    <div className="rounded-lg border border-line p-4">
      <h3 className={`text-sm font-semibold ${tone}`}>{label}</h3>
      <div className="mt-3 flex items-baseline gap-2">
        <span className="font-display text-3xl font-bold tabular-nums text-fg">{points}</span>
        <span className="text-sm text-fg-2">Punkte</span>
      </div>
      <p className="mt-1 text-sm text-fg-2">{average} Punkte pro Spiel · {hitRate} richtige Tendenzen</p>
    </div>
  )
}

function formatAverage(points: number, matches: number): string {
  return (points / matches).toLocaleString('de-CH', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
