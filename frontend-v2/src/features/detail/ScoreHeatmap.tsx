import { probColor } from '../../lib/util'
import { hasScoreMatrix } from '../../lib/prediction.mjs'
import { useAppState } from '../../state/AppState'
import type { Prediction } from '../../lib/types'

export function ScoreHeatmap({ calc, homeDisp, awayDisp }: {
  calc: Prediction; homeDisp: string; awayDisp: string
}) {
  const { light } = useAppState()
  const matrix = calc.matrix
  if (!matrix || !hasScoreMatrix(matrix)) return <p className="text-sm text-fg-3">Keine Ergebnistabelle verfügbar.</p>
  const maxP = calc.max_prob
    ?? Math.max(...Object.values(matrix).flatMap((row) => Object.values(row)), 0.0001)
  const goals = [0, 1, 2, 3, 4, 5]

  return (
    <div>
      <div className="mb-1 text-center text-[10px] font-bold uppercase tracking-widest text-fg-3">
        Tore von {awayDisp} →
      </div>
      <div className="flex items-center">
        <div
          className="pr-2 text-[10px] font-bold uppercase tracking-widest text-fg-3"
          style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}
        >
          Tore von {homeDisp}
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
            title={`${homeDisp} ${h}:${a} ${awayDisp} · ${(prob * 100).toFixed(1)} % Wahrscheinlichkeit`}
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
