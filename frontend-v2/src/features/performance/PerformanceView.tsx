import { GlassCard, SectionTitle } from '../../components/shared/GlassCard'
import { PageTransition, PageHeader } from '../../components/shared/PageTransition'
import { PerformanceSkeleton } from '../../components/shared/Skeleton'
import { QueryState } from '../../components/shared/QueryState'
import { usePerformanceData } from './usePerformanceData'
import { BotScoreboard } from './BotScoreboard'
import { PointsRaceChart } from './PointsRaceChart'
import { BuildABot } from './BuildABot'
import { MatchHistory } from './MatchHistory'
import { ForecastEvaluation } from './ForecastEvaluation'

export function PerformanceView() {
  const {
    archive, completed, totals, botStats, comparison, extraBots, customBot, simulate,
    isLoading, isError, retryArchive,
  } = usePerformanceData()

  if (isError && !archive) {
    return (
      <PageTransition>
        <PageHeader title="Tipps & Auswertung" subtitle="Gemeinsame Tipps und Modelltipps im Rückblick." />
        <QueryState
          title="Auswertung nicht verfügbar"
          message="Die gespeicherten Spieldaten konnten nicht geladen werden. Prüfe die Verbindung und versuche es erneut."
          onRetry={() => { void retryArchive() }}
        />
        <div className="mt-5"><ForecastEvaluation /></div>
      </PageTransition>
    )
  }

  if (isLoading) {
    return (
      <PageTransition>
        <PageHeader title="Tipps & Auswertung" subtitle="Gemeinsame Tipps und Modelltipps im Rückblick." />
        <PerformanceSkeleton />
        <div className="mt-5"><ForecastEvaluation /></div>
      </PageTransition>
    )
  }

  const commonTipRate = totals.userCount > 0 ? `${((totals.userCount / Math.max(totals.completed, 1)) * 100).toFixed(0)}%` : '—'
  const sharedPointsPerGame = comparison.matches > 0 ? formatAverage(comparison.userPoints, comparison.matches) : '—'
  const modelPointsPerGame = comparison.matches > 0 ? formatAverage(comparison.algoPoints, comparison.matches) : '—'

  return (
    <PageTransition>
      <PageHeader title="Tipps & Auswertung" subtitle="Gemeinsame Tipps und Modelltipps im Rückblick." />

      <div className="space-y-5">
        {isError && archive && (
          <QueryState
            title="Aktualisierung fehlgeschlagen"
            message="Die zuletzt gespeicherte Auswertung wird angezeigt. Neue Spieldaten konnten nicht geladen werden."
            onRetry={() => { void retryArchive() }}
          />
        )}
        <GlassCard>
          <SectionTitle className="mb-4">Übersicht</SectionTitle>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Kpi label="Abgeschlossene Spiele" value={String(totals.completed)} />
            <Kpi label="Gemeinsame Tipps" value={String(totals.userCount)} />
            <Kpi label="Anteil mit gemeinsamem Tipp" value={commonTipRate} />
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

        <GlassCard>
          <SectionTitle className="mb-2">Gemeinsame Tipps und Modell im fairen Vergleich</SectionTitle>
          <p className="mb-5 max-w-3xl text-sm leading-relaxed text-fg-2">
            Gezählt werden nur abgeschlossene Spiele mit gemeinsamem Tipp und gespeichertem Vorab-Modelltipp.
            Nachträglich rekonstruierte Elo-Tipps bleiben ausgeschlossen.
          </p>

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

        <MatchHistory completed={completed} hasReconstructed={totals.hasReconstructed} />

        <details className="group rounded-xl border border-line bg-surface">
          <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-semibold text-fg marker:hidden">
            <span>Weitere Auswertungen und Rücktests</span>
            <span aria-hidden="true" className="text-fg-3 transition group-open:rotate-180">⌄</span>
          </summary>
          <div className="space-y-4 border-t border-line p-4">
            <BotScoreboard totals={totals} botStats={botStats} extraBots={extraBots} />
            <BuildABot
              customBot={customBot}
              simulate={simulate}
              completed={completed}
              commonMatchIds={comparison.matchIds}
            />
            <PointsRaceChart completed={completed} commonMatchIds={comparison.matchIds} />
          </div>
        </details>
      </div>
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
