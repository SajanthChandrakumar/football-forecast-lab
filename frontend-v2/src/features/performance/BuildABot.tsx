import { useEffect, useRef, useState } from 'react'
import { useSaveCustomBot } from '../../hooks/queries'
import { useAppState } from '../../state/AppState'
import { botFormState, DEFAULT_BOT_PARAMS } from '../../lib/customBot.mjs'
import type { BotSimulation, CustomBot, CustomBotParams } from '../../lib/types'
import { GlassCard, SectionTitle } from '../../components/shared/GlassCard'
import { cn } from '../../lib/util'
import type { CompletedMatch, usePerformanceData } from './usePerformanceData'

const SLIDERS: { key: keyof CustomBotParams; label: string; min: number; max: number; step: number }[] = [
  { key: 'market_weight', label: 'Marktanteil', min: 0, max: 1, step: 0.05 },
  { key: 'risk', label: 'Risiko', min: -1, max: 1, step: 0.1 },
  { key: 'underdog_bias', label: 'Aussenseitergewichtung', min: 0, max: 6, step: 0.5 },
  { key: 'draw_bias', label: 'Unentschieden-Gewichtung', min: 0, max: 6, step: 0.5 },
]

function sliderValueLabel(key: keyof CustomBotParams, value: number): string {
  if (key === 'market_weight') return `Markt ${Math.round(value * 100)}% · Elo ${Math.round((1 - value) * 100)}%`
  if (key === 'risk') return value > 0 ? `Riskanter +${value.toFixed(1)}` : value < 0 ? `Vorsichtiger ${value.toFixed(1)}` : 'Ausgeglichen'
  return value <= 0 ? 'Aus' : `+${value.toFixed(1)}`
}

export function BuildABot({ customBot, simulate, completed, commonMatchIds }: {
  customBot: CustomBot | undefined
  simulate: ReturnType<typeof usePerformanceData>['simulate']
  completed: CompletedMatch[]
  commonMatchIds: string[]
}) {
  const { competition } = useAppState()
  const [params, setParams] = useState<CustomBotParams>(DEFAULT_BOT_PARAMS)
  const [name, setName] = useState('Mein Bot')
  const [sim, setSim] = useState<BotSimulation | null>(null)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const save = useSaveCustomBot()
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const runIdRef = useRef(0)

  useEffect(() => {
    const state = botFormState(customBot)
    setParams(state.params)
    setName(state.name)
    setSim(null)
    setSaveState('idle')
  }, [customBot, competition])

  useEffect(() => {
    const runId = ++runIdRef.current
    if (timer.current) clearTimeout(timer.current)
    setSim(null)
    timer.current = setTimeout(() => {
      simulate.mutate(params, {
        onSuccess: (result) => { if (runId === runIdRef.current) setSim(result) },
      })
    }, 300)
    return () => { if (timer.current) clearTimeout(timer.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params, competition])

  const retrySimulation = () => {
    const runId = ++runIdRef.current
    simulate.mutate(params, {
      onSuccess: (result) => { if (runId === runIdRef.current) setSim(result) },
    })
  }

  const onSave = () => {
    setSaveState('saving')
    save.mutate(
      { name: name || 'Mein Bot', params },
      {
        onSuccess: () => setSaveState('saved'),
        onError: () => setSaveState('error'),
      },
    )
  }

  const comparableIds = new Set(commonMatchIds)
  const simulatedCommon = new Set((sim?.breakdown ?? []).filter(({ match_id }) => comparableIds.has(match_id)).map(({ match_id }) => match_id))
  const commonRows = completed.filter(({ id }) => simulatedCommon.has(id))
  const botCommonPoints = (sim?.breakdown ?? [])
    .filter(({ match_id }) => simulatedCommon.has(match_id))
    .reduce((total, row) => total + row.points, 0)
  const sharedCommonPoints = commonRows.reduce((total, row) => total + row.points, 0)
  const modelCommonPoints = commonRows.reduce((total, row) => total + (row.entry.post_match_result.algo_points ?? 0), 0)

  return (
    <GlassCard>
      <SectionTitle className="mb-2">Eigenen Bot testen</SectionTitle>
      <p className="mb-5 max-w-3xl text-sm leading-relaxed text-fg-2">
        Stelle eine Tippstrategie ein. Der Rücktest nutzt abgeschlossene Spiele mit verfügbaren Vorhersagedaten.
        Der Vergleich mit gemeinsamen Tipps und Modell wird zusätzlich auf dieselben Spiele begrenzt.
      </p>

      <div className="grid gap-x-6 gap-y-5 sm:grid-cols-2">
        {SLIDERS.map(({ key, label, min, max, step }) => {
          const id = `bot-${key}`
          return (
            <div key={key}>
              <div className="mb-2 flex items-baseline justify-between gap-3">
                <label htmlFor={id} className="text-sm font-medium text-fg">{label}</label>
                <span className="text-xs font-semibold text-blue-a">{sliderValueLabel(key, params[key])}</span>
              </div>
              <input
                id={id}
                type="range"
                min={min}
                max={max}
                step={step}
                value={params[key]}
                aria-valuetext={sliderValueLabel(key, params[key])}
                onChange={(event) => setParams((current) => ({ ...current, [key]: Number(event.target.value) }))}
                className="h-6 w-full cursor-pointer accent-blue-a"
              />
            </div>
          )
        })}
      </div>

      <div className="mt-5 min-h-20 border-t border-line pt-4" aria-live="polite">
        {sim?.matches === 0 ? (
          <div className="rounded-lg border border-line bg-surface px-4 py-3 text-sm text-fg-2">
            Für diesen Rücktest fehlen auswertbare Spiele. Benötigt werden abgeschlossene Spiele mit den nötigen Vorhersagedaten.
          </div>
        ) : sim ? (
          <>
            <p className="text-sm font-semibold text-fg">Rücktest: {sim.total_points} Punkte aus {sim.matches} auswertbaren Spielen</p>
            {commonRows.length > 0 ? (
              <div className="mt-3 grid gap-2 sm:grid-cols-3">
                <ComparablePoints label="Gemeinsame Tipps" points={sharedCommonPoints} matches={commonRows.length} />
                <ComparablePoints label="Modell" points={modelCommonPoints} matches={commonRows.length} />
                <ComparablePoints label="Eigener Bot" points={botCommonPoints} matches={commonRows.length} />
              </div>
            ) : (
              <p className="mt-2 text-sm text-fg-2">
                Keine Spiele dieses Rücktests gehören zur gemeinsamen Vergleichsstichprobe; deshalb gibt es keinen Punktevergleich.
              </p>
            )}
          </>
        ) : simulate.isError ? (
          <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line px-4 py-3">
            <p className="text-sm text-fg-2">Der Rücktest ist fehlgeschlagen. Du kannst ihn erneut starten.</p>
            <button type="button" onClick={retrySimulation} className="min-h-10 rounded-lg border border-line-2 px-3 text-sm font-semibold text-fg hover:bg-surface-2">Erneut versuchen</button>
          </div>
        ) : (
          <p className="text-sm text-fg-2">{simulate.isPending ? 'Rücktest wird berechnet …' : 'Regler ändern, um den Rücktest zu berechnen.'}</p>
        )}
      </div>

      <div className="mt-5 flex flex-wrap items-end gap-3 border-t border-line pt-4">
        <div className="min-w-48 flex-1">
          <label htmlFor="custom-bot-name" className="mb-1.5 block text-sm font-medium text-fg">Name des Bots</label>
          <input
            id="custom-bot-name"
            value={name}
            onChange={(event) => { setName(event.target.value); setSaveState('idle') }}
            maxLength={40}
            className="min-h-11 w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-fg outline-none focus:border-blue-a"
          />
        </div>
        <button
          type="button"
          onClick={onSave}
          disabled={saveState === 'saving'}
          className={cn(
            'min-h-11 rounded-lg border px-4 py-2 text-sm font-semibold transition disabled:opacity-50',
            saveState === 'error' ? 'border-red-a text-red-a' : 'border-blue-a bg-blue-a/10 text-blue-a hover:bg-blue-a/15',
          )}
        >
          {saveState === 'saving' ? 'Wird gespeichert …' : 'Bot speichern'}
        </button>
        {saveState === 'saved' && <span role="status" className="text-sm text-fg-2">Bot gespeichert.</span>}
        {saveState === 'error' && <span role="alert" className="text-sm text-red-a">Speichern fehlgeschlagen. Bitte erneut versuchen.</span>}
      </div>
    </GlassCard>
  )
}

function ComparablePoints({ label, points, matches }: { label: string; points: number; matches: number }) {
  return (
    <div className="rounded-lg border border-line p-3">
      <p className="text-xs font-medium text-fg-2">{label}</p>
      <p className="mt-1 font-display text-2xl font-bold tabular-nums text-fg">{points}</p>
      <p className="text-xs text-fg-3">{(points / matches).toLocaleString('de-CH', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} Punkte pro Spiel · {matches} Spiele</p>
    </div>
  )
}
