import { useQuery } from '@tanstack/react-query'
import { GlassCard, SectionTitle } from '../../components/shared/GlassCard'
import { useAppState } from '../../state/AppState'

interface CalibrationBin {
  range: string
  count: number
  mean_confidence: number
  observed_accuracy: number
}

interface ModelResult {
  id: 'model' | 'bookmaker' | 'elo'
  label: string
  n: number
  brier: number | null
  log_loss: number | null
  accuracy: number | null
  calibration: CalibrationBin[]
}

interface ModelComparisonResult {
  competition: string
  counts: {
    total_completed: number
    verified_model: number
    paired: number
    missing_baselines: number
    excluded: number
  }
  models: ModelResult[]
}

async function loadComparison(competition: string): Promise<ModelComparisonResult> {
  const response = await fetch(`/api/model-comparison?competition=${encodeURIComponent(competition)}`)
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
  return response.json() as Promise<ModelComparisonResult>
}

function score(value: number | null, digits = 3) {
  return value == null ? '—' : value.toFixed(digits)
}

export function ModelComparison() {
  const { competition } = useAppState()
  const { data, isLoading, isError } = useQuery({
    queryKey: ['modelComparison', competition],
    queryFn: () => loadComparison(competition),
    staleTime: 300_000,
    retry: false,
  })

  return (
    <GlassCard>
      <SectionTitle className="mb-3">Vorab-Prognosen im Vergleich</SectionTitle>
      {isLoading ? (
        <p className="text-sm text-fg-3">Vergleich wird geladen …</p>
      ) : isError || !data ? (
        <p className="text-sm text-fg-3">Der Vergleich ist gerade nicht verfügbar.</p>
      ) : (
        <>
          <p className="mb-3 text-sm leading-relaxed text-fg-2">
            Alle drei Werte nutzen dieselben Spiele mit belegten Wahrscheinlichkeiten vor dem Anpfiff.
          </p>
          <div className="space-y-2">
            {data.models.map((model) => (
              <div key={model.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-xl border border-line bg-surface px-3 py-2.5">
                <span className="min-w-0 text-sm font-semibold text-fg">{model.label}</span>
                <span className="text-right">
                  <span className="block text-[10px] font-semibold uppercase tracking-wider text-fg-3">Brier · kleiner besser</span>
                  <span className="tabular-nums text-sm text-fg">{score(model.brier)}</span>
                </span>
              </div>
            ))}
          </div>

          <p className="mt-3 text-xs leading-relaxed text-fg-3">
            Gemeinsame Stichprobe: {data.counts.paired} von {data.counts.total_completed} abgeschlossenen Spielen.
            {' '}{data.counts.verified_model} Modellprognosen sind vor dem Anpfiff eingefroren; bei {data.counts.missing_baselines} fehlen belegbare Buchmacher- oder Elo-Werte.
            {' '}{data.counts.excluded} ältere, rekonstruierte oder anderweitig nicht belegbare Spiele sind ausgeschlossen.
          </p>

          {data.counts.paired === 0 && (
            <p className="mt-3 rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm leading-relaxed text-fg-2">
              Für diese Spielauswertung gibt es noch keinen gemeinsamen, verifizierbaren Vorab-Vergleich. Künftig erscheinen hier abgeschlossene Spiele mit rechtzeitig eingefrorener Prognose und belegten Buchmacher- und Elo-Werten.
            </p>
          )}
          {data.counts.paired > 0 && data.counts.paired < 30 && (
            <p className="mt-3 rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm leading-relaxed text-fg-2">
              Bei nur {data.counts.paired} Spielen ist das eine erste Orientierung; daraus lässt sich noch keine verlässliche Rangfolge ableiten.
            </p>
          )}

          <details className="mt-3 border-t border-line pt-3">
            <summary className="cursor-pointer text-xs font-semibold text-fg-2">Weitere Kennzahlen und Kalibrierung</summary>
            <div className="mt-3 space-y-4">
              {data.models.map((model) => (
                <section key={model.id}>
                  <h3 className="mb-1 text-xs font-semibold text-fg">{model.label}</h3>
                  <p className="text-xs text-fg-3">
                    Log Loss: {score(model.log_loss)} · 1X2-Treffer: {model.accuracy == null ? '—' : `${(model.accuracy * 100).toFixed(1)}%`}
                  </p>
                  <p className="mt-1 text-xs text-fg-3">Kalibrierung nach höchster vorhergesagter Wahrscheinlichkeit: Erwartung / eingetroffene Treffer.</p>
                  {model.calibration.length > 0 ? (
                    <ul className="mt-1 space-y-1 text-xs text-fg-3">
                      {model.calibration.map((bin) => (
                        <li key={bin.range}>
                          {bin.range}: {(bin.mean_confidence * 100).toFixed(0)}% erwartet, {(bin.observed_accuracy * 100).toFixed(0)}% eingetroffen ({bin.count} Spiele)
                        </li>
                      ))}
                    </ul>
                  ) : <p className="mt-1 text-xs text-fg-3">Noch keine Kalibrierungswerte.</p>}
                </section>
              ))}
              <p className="text-xs leading-relaxed text-fg-3">
                Brier und Log Loss bewerten die vorhergesagten Wahrscheinlichkeiten; bei beiden ist ein kleinerer Wert besser. Die Trefferquote zählt nur den wahrscheinlichsten Ausgang. Eine kleine Stichprobe belegt keine Überlegenheit.
              </p>
            </div>
          </details>
        </>
      )}
    </GlassCard>
  )
}
