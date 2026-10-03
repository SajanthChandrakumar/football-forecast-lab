import { probColor } from '../../lib/util'
import { hasScoreMatrix } from '../../lib/prediction.mjs'
import { scoreProbabilitySummary } from '../../lib/tip-insights.mjs'
import { useAppState } from '../../state/AppState'
import type { Prediction } from '../../lib/types'

export function ScoreHeatmap({ calc, modelTip, homeDisp, awayDisp }: {
  calc: Prediction; modelTip?: string | null; homeDisp: string; awayDisp: string
}) {
  const { light } = useAppState()
  const matrix = calc.matrix
  if (!matrix || !hasScoreMatrix(matrix)) return <p className="text-sm text-fg-3">Keine Ergebniswahrscheinlichkeiten verfügbar.</p>
  const maxP = calc.max_prob
    ?? Math.max(...Object.values(matrix).flatMap((row) => Object.values(row)), 0.0001)
  const goals = [0, 1, 2, 3, 4, 5]
  const summary = scoreProbabilitySummary(matrix, modelTip)

  return (
    <div>
      {summary && (
        <div className="mb-4 space-y-3">
          <p className="text-sm font-semibold text-fg">Die wahrscheinlichsten einzelnen Ergebnisse</p>
          <ol className="grid grid-cols-3 gap-2">
            {summary.topScores.map(({ tip, chance }) => (
              <li key={tip} className="rounded-xl bg-surface-2 px-2 py-3 text-center">
                <span className="block display-num text-xl text-fg">{tip}</span>
                <span className="block text-xs text-fg-2">{(chance * 100).toFixed(1)} % Chance</span>
              </li>
            ))}
          </ol>
          {modelTip && summary.modelTipChance !== null && (
            <p className="rounded-lg border border-line px-3 py-2 text-xs leading-relaxed text-fg-2">
              Modelltipp <strong className="text-fg">{modelTip}</strong> hat {(summary.modelTipChance * 100).toFixed(1)} % Chance, exakt einzutreffen. Er wird nach erwarteten Tippspielpunkten gewählt – deshalb muss er nicht das wahrscheinlichste Einzelergebnis sein.
            </p>
          )}
        </div>
      )}
      <details className="border-t border-line pt-3">
        <summary className="cursor-pointer text-sm font-semibold text-emerald-a">Alle Ergebniswahrscheinlichkeiten ansehen</summary>
        <div className="mt-4">
      <div className="mb-1 text-center text-[10px] font-bold uppercase tracking-widest text-fg-3">
        {awayDisp}: Tore →
      </div>
      <div className="flex items-center">
        <div
          className="pr-2 text-[10px] font-bold uppercase tracking-widest text-fg-3"
          style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}
        >
          {homeDisp}: Tore
        </div>
        <div className="grid flex-1 grid-cols-[24px_repeat(6,1fr)] gap-1">
          <div />
          {goals.map((a) => (
            <div key={a} className="text-center text-xs font-bold text-fg-3">{a}</div>
          ))}
          {goals.map((h) => (
            <FragmentRow key={h} h={h} matrix={matrix} maxP={maxP} light={light} homeDisp={homeDisp} awayDisp={awayDisp} />
          ))}
        </div>
      </div>
        </div>
      </details>
    </div>
  )
}

function FragmentRow({ h, matrix, maxP, light, homeDisp, awayDisp }: {
  h: number; matrix: Record<number, Record<number, number>>; maxP: number; light: boolean; homeDisp: string; awayDisp: string
}) {
  return (
    <>
      <div className="flex items-center justify-center text-xs font-bold text-fg-3">{h}</div>
      {[0, 1, 2, 3, 4, 5].map((a) => {
        const prob = matrix[h]?.[a] ?? 0
        const bg = probColor(prob, maxP, light)
        const textColor = prob / maxP > 0.5 ? 'rgba(0,0,0,0.85)' : light ? 'rgba(30,30,30,0.7)' : 'rgba(255,255,255,0.85)'
        return (
          <div
            key={a}
            title={`${homeDisp} ${h}:${a} ${awayDisp} — ${(prob * 100).toFixed(1)}%`}
            className="flex aspect-[2/1] items-center justify-center rounded text-[11px] font-semibold tabular-nums"
            style={{ background: bg, color: textColor }}
          >
            {(prob * 100).toFixed(1)}%
          </div>
        )
      })}
    </>
  )
}
