import { useMemo, useState } from 'react'
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { GlassCard, SectionTitle } from '../../components/shared/GlassCard'
import { cn } from '../../lib/util'
import { HOUSE_BOTS, type CompletedMatch, type ScoreRow } from './usePerformanceData'

/** Cumulative points per predictor over the played matches (oldest → newest). */
export function PointsRaceChart({ completed, extraBots }: {
  completed: CompletedMatch[]
  extraBots: ScoreRow[]
}) {
  const [hidden, setHidden] = useState<Set<string>>(new Set())

  const { rows, series } = useMemo(() => {
    const chrono = completed
      .sort((a, b) => a.sortDate.localeCompare(b.sortDate))
    const series = [
      { key: 'Du', color: '#d4af37', dash: '6 3' },
      { key: 'Algo gesamt', color: '#60a5fa', dash: '3 3' },
      ...HOUSE_BOTS.map((b) => ({ key: b.label, color: b.color, dash: undefined as string | undefined })),
      ...extraBots.map((b) => ({ key: b.label, color: b.color, dash: undefined as string | undefined })),
    ]
    const running: Record<string, number> = Object.fromEntries(series.map((s) => [s.key, 0]))

    const rows = chrono.map(({ id, entry, points }) => {
      const label = `${entry.metadata.home_team.slice(0, 3).toUpperCase()}–${entry.metadata.away_team.slice(0, 3).toUpperCase()}`
      running['Du'] += points
      running['Algo gesamt'] += entry.post_match_result.algo_points ?? 0
      const bp = entry.post_match_result.bot_points ?? {}
      for (const b of HOUSE_BOTS) running[b.label] += bp[b.key] ?? 0
      for (const eb of extraBots) running[eb.label] += eb.pointsByMatch?.[id] ?? 0
      return { label, ...running }
    })
    return { rows, series }
  }, [completed, extraBots])

  if (rows.length < 2) return null

  const toggle = (key: string) => setHidden((prev) => {
    const next = new Set(prev)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    return next
  })

  // Thin out X-axis labels once there are many matches, so they don't overlap into a smudge.
  const tickInterval = rows.length > 24 ? Math.ceil(rows.length / 12) : rows.length > 12 ? 1 : 0

  return (
    <GlassCard>
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <SectionTitle>Points Race</SectionTitle>
        <span className="text-[11px] text-fg-3">Klick auf einen Namen zum Ein-/Ausblenden</span>
      </div>

      {/* Custom legend: toggle chips instead of Recharts' cramped one-liner */}
      <div className="mb-3 flex flex-wrap gap-1.5">
        {series.map((s) => {
          const off = hidden.has(s.key)
          return (
            <button
              key={s.key}
              onClick={() => toggle(s.key)}
              className={cn(
                'flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold transition',
                off
                  ? 'border-line bg-surface text-fg-3 opacity-50'
                  : 'border-line-2 bg-surface-2 text-fg',
              )}
            >
              <span
                className="h-2 w-2 rounded-full"
                style={{ background: off ? 'var(--text-3)' : s.color }}
              />
              {s.key}
            </button>
          )
        })}
      </div>

      <div className="h-96">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 4, right: 16, bottom: 12, left: -4 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fill: 'var(--text-3)', fontSize: 10 }}
              interval={tickInterval}
              angle={-40}
              textAnchor="end"
              height={56}
              tickMargin={8}
              tickLine={false}
              axisLine={{ stroke: 'var(--border)' }}
            />
            <YAxis tick={{ fill: 'var(--text-3)', fontSize: 11 }} tickLine={false} axisLine={false} width={44} />
            <Tooltip
              contentStyle={{
                background: 'var(--surface-2)', border: '1px solid var(--border-2)',
                borderRadius: 12, fontSize: 12, backdropFilter: 'blur(14px)',
              }}
              labelStyle={{ color: 'var(--text-2)', fontWeight: 700 }}
            />
            {series.map((s) => (
              <Line
                key={s.key} type="monotone" dataKey={s.key}
                stroke={s.color} strokeWidth={s.key === 'Du' ? 3 : 2}
                strokeDasharray={s.dash} dot={false} activeDot={{ r: 4 }}
                hide={hidden.has(s.key)}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </GlassCard>
  )
}
