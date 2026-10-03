import { useMemo, useState } from 'react'
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { GlassCard, SectionTitle } from '../../components/shared/GlassCard'
import { cn } from '../../lib/util'
import type { CompletedMatch } from './usePerformanceData'

/** Points on the same common pre-match sample shown in the main comparison. */
export function PointsRaceChart({ completed, commonMatchIds }: {
  completed: CompletedMatch[]
  commonMatchIds: string[]
}) {
  const [hidden, setHidden] = useState<Set<string>>(new Set())

  const { rows, series } = useMemo(() => {
    const commonIds = new Set(commonMatchIds)
    const chrono = completed
      .filter(({ id }) => commonIds.has(id))
      .sort((a, b) => a.sortDate.localeCompare(b.sortDate))
    const series = [
      { key: 'Gemeinsame Tipps', color: 'var(--gold)', dash: '6 3' },
      { key: 'Modell', color: 'var(--blue)', dash: undefined as string | undefined },
    ]
    let sharedTotal = 0
    let modelTotal = 0
    const rows = chrono.map(({ entry, points }) => {
      sharedTotal += points
      modelTotal += entry.post_match_result.algo_points ?? 0
      return {
        label: `${entry.metadata.home_team.slice(0, 3).toUpperCase()}–${entry.metadata.away_team.slice(0, 3).toUpperCase()}`,
        'Gemeinsame Tipps': sharedTotal,
        Modell: modelTotal,
      }
    })
    return { rows, series }
  }, [completed, commonMatchIds])

  if (rows.length < 2) return null

  const toggle = (key: string) => setHidden((previous) => {
    const next = new Set(previous)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    return next
  })

  const tickInterval = rows.length > 24 ? Math.ceil(rows.length / 12) : rows.length > 12 ? 1 : 0

  return (
    <GlassCard>
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <SectionTitle>Punkteverlauf im gemeinsamen Vergleich</SectionTitle>
        <span className="text-xs text-fg-3">Nur gemeinsame Vergleichsspiele</span>
      </div>

      <div className="mb-3 flex flex-wrap gap-2" aria-label="Kurven auswählen">
        {series.map((item) => {
          const isHidden = hidden.has(item.key)
          return (
            <button
              key={item.key}
              type="button"
              aria-pressed={!isHidden}
              onClick={() => toggle(item.key)}
              className={cn(
                'min-h-10 rounded-lg border px-3 py-1.5 text-xs font-semibold transition',
                isHidden ? 'border-line bg-surface text-fg-3' : 'border-line-2 bg-surface-2 text-fg',
              )}
            >
              <span className="mr-2 inline-block h-2 w-2 rounded-full" style={{ background: item.color }} aria-hidden="true" />
              {item.key}
            </button>
          )
        })}
      </div>

      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 4, right: 16, bottom: 12, left: -4 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fill: 'var(--text-3)', fontSize: 10 }}
              interval={tickInterval}
              angle={-35}
              textAnchor="end"
              height={52}
              tickMargin={8}
              tickLine={false}
              axisLine={{ stroke: 'var(--border)' }}
            />
            <YAxis tick={{ fill: 'var(--text-3)', fontSize: 11 }} tickLine={false} axisLine={false} width={44} />
            <Tooltip
              contentStyle={{
                background: 'var(--surface-2)', border: '1px solid var(--border-2)',
                borderRadius: 8, fontSize: 12,
              }}
              labelStyle={{ color: 'var(--text-2)', fontWeight: 600 }}
            />
            {series.map((item) => (
              <Line
                key={item.key}
                type="monotone"
                dataKey={item.key}
                stroke={item.color}
                strokeWidth={item.key === 'Modell' ? 2.5 : 2}
                strokeDasharray={item.dash}
                dot={false}
                activeDot={{ r: 4 }}
                hide={hidden.has(item.key)}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </GlassCard>
  )
}
