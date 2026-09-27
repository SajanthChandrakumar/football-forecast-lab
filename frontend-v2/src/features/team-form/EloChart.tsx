import { useMemo } from 'react'
import {
  CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { teamsWithoutHistory } from '../../lib/team-form.mjs'
import type { EloHistory } from '../../lib/types'
import type { MatchInfo } from './useTeamFormData'

const LINE_COLORS = ['#10b981', '#d4af37', '#5b9bd5', '#9b6dd1', '#de7a76', '#d9a441', '#4dd0c4', '#9a9a9a']

interface Props {
  teams: string[]
  history: EloHistory | undefined
  matchInfo: Record<string, Record<string, MatchInfo>>
}

interface ChartRow {
  label: string
  ts: number
  [team: string]: string | number | null | undefined
}

/** Union of all selected teams' timestamps → one categorical row per moment. */
function buildRows(teams: string[], history: EloHistory | undefined): ChartRow[] {
  if (!history) return []
  const tsSet = new Set<number>()
  for (const t of teams) for (const p of history[t] ?? []) tsSet.add(p.timestamp)
  const ordered = [...tsSet].sort((a, b) => a - b)

  return ordered.map((ts) => {
    const row: ChartRow = {
      ts,
      label: ts === 0
        ? 'Start'
        : new Date(ts * 1000).toLocaleDateString('de-CH', { day: '2-digit', month: '2-digit' }),
    }
    for (const t of teams) {
      const p = (history[t] ?? []).find((x) => x.timestamp === ts)
      if (p) {
        row[t] = Math.round(p.elo)
        row[`${t}__match`] = p.match_id
      } else {
        // Recharts' connectNulls needs explicit null, not a missing key.
        row[t] = null
      }
    }
    return row
  })
}

const RESULT_LABEL = { W: 'S', D: 'U', L: 'N' } as const

export function EloChart({ teams, history, matchInfo }: Props) {
  const rows = useMemo(() => buildRows(teams, history), [teams, history])
  const currentOnly = useMemo(() => teamsWithoutHistory(teams, history), [teams, history])

  if (teams.length === 0) {
    return <p className="py-10 text-center text-sm text-fg-3">Wähle bis zu 4 Teams für den Vergleich.</p>
  }

  return (
    <>
      {currentOnly.length > 0 && (
        <p className="mb-3 text-xs leading-relaxed text-fg-3">
          Nur die aktuelle Elo-Bewertung liegt vor für {currentOnly.join(', ')}; ein historischer Verlauf ist nicht verfügbar.
        </p>
      )}
      {rows.length > 0 && (
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: -8 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" tick={{ fill: 'var(--text-3)', fontSize: 11 }} tickLine={false} axisLine={{ stroke: 'var(--border)' }} />
              <YAxis domain={['auto', 'auto']} tick={{ fill: 'var(--text-3)', fontSize: 11 }} tickLine={false} axisLine={false} width={48} />
              <Tooltip content={<EloTooltip matchInfo={matchInfo} />} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {teams.map((t, i) => (
                <Line
                  key={t}
                  type="monotone"
                  dataKey={t}
                  stroke={LINE_COLORS[i % LINE_COLORS.length]}
                  strokeWidth={2.5}
                  dot={{ r: 3, strokeWidth: 0, fill: LINE_COLORS[i % LINE_COLORS.length] }}
                  activeDot={{ r: 5 }}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      {rows.length === 0 && currentOnly.length === 0 && (
        <p className="py-10 text-center text-sm text-fg-3">Für die Auswahl liegen keine historischen Elo-Daten vor.</p>
      )}
    </>
  )
}

interface TooltipProps {
  active?: boolean
  label?: string
  payload?: { dataKey: string; value: number; color: string; payload: ChartRow }[]
  matchInfo: Record<string, Record<string, MatchInfo>>
}

function EloTooltip({ active, label, payload, matchInfo }: TooltipProps) {
  if (!active || !payload?.length) return null
  return (
    <div className="glass !rounded-xl px-3 py-2 text-xs shadow-xl">
      <div className="mb-1 font-bold text-fg-2">{label}</div>
      {payload.map((entry) => {
        const team = entry.dataKey
        const matchId = entry.payload[`${team}__match`] as string | undefined
        const info = matchId ? matchInfo[team]?.[matchId] : undefined
        return (
          <div key={team} className="flex items-center gap-2 py-0.5">
            <span className="h-2 w-2 rounded-full" style={{ background: entry.color }} />
            <span className="font-semibold text-fg">{team}:</span>
            <span className="tabular-nums text-fg-2">{entry.value}</span>
            {info && (
              <span className="text-fg-3">
                · {info.score} vs {info.opponent} ({RESULT_LABEL[info.result]})
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}
