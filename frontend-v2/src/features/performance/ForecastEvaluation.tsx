import { GlassCard, SectionTitle } from '../../components/shared/GlassCard'
import { QueryState } from '../../components/shared/QueryState'
import { useModelEvaluation } from '../../hooks/queries'

const METHODS = [['model', 'Modell'], ['market', 'Markt ohne Buchmachermarge'], ['elo', 'Elo']] as const
const REASONS: Record<string, string> = {
  missing_capture: 'Keine gespeicherte Vorab-Aufnahme',
  reconstructed_capture: 'Nachträglich rekonstruierte Prognose',
  missing_capture_timestamp: 'Aufnahme- oder Anstoßzeit fehlt',
  invalid_capture_timestamp: 'Aufnahme- oder Anstoßzeit ungültig',
  kickoff_mismatch: 'Abweichende Anstoßzeit',
  after_kickoff_capture: 'Aufnahme nach Anstoß',
  outside_capture_window: 'Aufnahme außerhalb von T−15 bis vor T−5',
  missing_source_timestamp: 'Zeitpunkt einer Datenquelle fehlt',
  invalid_source_timestamp: 'Datenquelle ungültig oder zu spät erfasst',
  missing_model_version: 'Modellversion fehlt',
  invalid_probability_vector: 'Unvollständige oder ungültige Wahrscheinlichkeiten',
  ambiguous_ko_result: 'K.-o.-Ergebnis nach 90 Minuten nicht eindeutig',
  invalid_90_minute_score: 'Ungültiges Ergebnis nach 90 Minuten',
  invalid_result: 'Auswertbares Ergebnis fehlt',
}
const formatMetric = (value: number | null) => value === null ? '—' : value.toLocaleString('de-CH', { minimumFractionDigits: 3, maximumFractionDigits: 3 })

export function ForecastEvaluation() {
  const { data, isPending, isError, refetch } = useModelEvaluation()
  return (
    <GlassCard>
      <SectionTitle>Wahrscheinlichkeitsgüte</SectionTitle>
      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-fg-2">
        Wie gut wurden Heimsieg, Remis und Auswärtssieg vorhergesagt? Alle drei Methoden werden auf denselben Spielen und dem Ergebnis nach 90 Minuten verglichen.
      </p>
      {isPending && <p role="status" className="mt-5 text-sm text-fg-2">Vorab-Prognosen werden geladen …</p>}
      {isError && <div className="mt-4"><QueryState title="Prognoseauswertung nicht verfügbar" message="Die gespeicherten Wahrscheinlichkeiten konnten nicht geladen werden." onRetry={() => { void refetch() }} /></div>}
      {data && <>
        <div className="mt-5 flex flex-wrap items-baseline justify-between gap-2 border-b border-line pb-4">
          <p className="text-sm font-semibold text-fg">{data.common_sample_count} {data.common_sample_count === 1 ? 'Spiel' : 'Spiele'} in der gemeinsamen Stichprobe</p>
          <p className="text-xs text-fg-3">{data.common_sample_count} von {data.completed_count} abgeschlossenen Spielen auswertbar</p>
        </div>
        {data.common_sample_count === 0 ? (
          <p role="status" className="mt-4 rounded-lg border border-line bg-surface p-4 text-sm leading-relaxed text-fg-2">
            Noch keine auswertbaren Vorab-Prognosen. Künftige Aufnahmen entstehen bei der Wartung zwischen 15 und 5 Minuten vor Anstoß, wenn Quoten und Elo-Daten mit bekanntem Zeitpunkt vorliegen. Alte Spiele werden nicht nachträglich ergänzt.
          </p>
        ) : (
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            {METHODS.map(([method, label]) => <div key={method} className="min-w-0 rounded-lg border border-line p-4">
              <h3 className="min-h-10 text-sm font-semibold text-fg">{label}</h3>
              <dl className="mt-3 space-y-3">
                <div className="flex items-baseline justify-between gap-2"><dt className="text-sm text-fg-2">Brier</dt><dd className="font-display text-2xl font-bold tabular-nums text-fg">{formatMetric(data.metrics[method].brier_score)}</dd></div>
                <div className="flex items-baseline justify-between gap-2"><dt className="text-sm text-fg-2">Log Loss</dt><dd className="font-display text-2xl font-bold tabular-nums text-fg">{formatMetric(data.metrics[method].log_loss)}</dd></div>
              </dl>
            </div>)}
          </div>
        )}
        <details className="group mt-4 border-t border-line pt-3">
          <summary className="min-h-11 cursor-pointer py-2 text-sm font-semibold text-fg">Datengrundlage und Kennzahlen</summary>
          <div className="mt-2 space-y-4 text-sm leading-relaxed text-fg-2">
            <p>{data.captured_count} abgeschlossene Spiele mit gespeicherter Aufnahme. Ausgeschlossen: {data.completed_count - data.common_sample_count}. Fehlende Daten können die Stichprobe verzerren.</p>
            {Object.keys(data.exclusions).length > 0 && <dl className="space-y-2">{Object.entries(data.exclusions).map(([reason, count]) => <div key={reason} className="flex justify-between gap-4"><dt>{REASONS[reason] ?? reason}</dt><dd className="shrink-0 tabular-nums text-fg">{count}</dd></div>)}</dl>}
            <p><b className="text-fg">Brier (0 bis 2):</b> Durchschnitt der Summe der drei quadrierten Abweichungen vom tatsächlichen Ausgang. Kleinere Werte bedeuten geringere Fehler.</p>
            <p><b className="text-fg">Log Loss:</b> Durchschnitt von −ln der Wahrscheinlichkeit des tatsächlichen Ausgangs. Sehr sichere Fehlprognosen zählen stark. Kleinere Werte sind besser; für die Berechnung gilt eine Untergrenze von 10⁻¹⁵.</p>
            <p>Das sind Wahrscheinlichkeiten für den Spielausgang, keine Sicherheit eines exakten Ergebnistipps. Tippspielpunkte werden separat ausgewertet.</p>
          </div>
        </details>
      </>}
    </GlassCard>
  )
}
