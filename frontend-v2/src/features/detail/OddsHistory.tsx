import { useQuery } from '@tanstack/react-query'
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { useAppState } from '../../state/AppState'

type Outcome = 'home' | 'draw' | 'away'
type OddsHistoryPoint = {
  observed_at: string
  bucket: string
  source: string
  odds: Record<Outcome, number>
  probabilities: Record<Outcome, number>
}
type OddsHistoryData = {
  match_id: string
  competition: string
  status: 'available' | 'unavailable'
  observations: OddsHistoryPoint[]
  probability_change_pp?: Record<Outcome, number>
}

const OUTCOMES: { key: Outcome; label: string }[] = [
  { key: 'home', label: 'Heim' },
  { key: 'draw', label: 'Remis' },
  { key: 'away', label: 'Auswärts' },
]
const BUCKET_LABEL: Record<string, string> = {
  t24h: 'T−24 h', t6h: 'T−6 h', t75m: 'T−75 min', t30m: 'T−30 min', t15m: 'T−15 min', manual: 'Manuell',
}
const COLORS: Record<Outcome, string> = { home: '#547a63', draw: '#778078', away: '#ae895c' }

function probability(value: number) {
  return `${(value * 100).toLocaleString('de-CH', { maximumFractionDigits: 1 })} %`
}

function signedPoints(value: number) {
  const formatted = Math.abs(value).toLocaleString('de-CH', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
  return `${value > 0 ? '+' : value < 0 ? '−' : ''}${formatted} Prozentpunkte`
}

function observedTime(value: string) {
  return new Date(value).toLocaleString('de-CH', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Zurich',
  })
}

function OddsHistoryChart({ observations, homeTeam, awayTeam }: {
  observations: OddsHistoryPoint[]; homeTeam: string; awayTeam: string
}) {
  const data = observations.map((point) => ({
    bucketLabel: BUCKET_LABEL[point.bucket] ?? point.bucket,
    Heim: point.probabilities.home * 100,
    Remis: point.probabilities.draw * 100,
    Auswärts: point.probabilities.away * 100,
  }))
  return (
    <div role="img" aria-label={`Bereinigte 1X2-Wahrscheinlichkeit für ${homeTeam}, Remis und ${awayTeam}`} className="mt-4 h-44 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="bucketLabel" tick={{ fill: 'var(--text-3)', fontSize: 10 }} tickLine={false} axisLine={false} />
          <YAxis domain={[0, 100]} tickFormatter={(value) => `${value}%`} tick={{ fill: 'var(--text-3)', fontSize: 10 }} tickLine={false} axisLine={false} />
          <Tooltip formatter={(value) => `${Number(value).toFixed(1)} %`} contentStyle={{ borderRadius: 12, borderColor: 'var(--border)', background: 'var(--surface)' }} />
          {OUTCOMES.map(({ key, label }) => (
            <Line key={key} type="monotone" dataKey={label} stroke={COLORS[key]} strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 4 }} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export function OddsHistory({ matchId, homeTeam, awayTeam, enabled = true }: {
  matchId: string; homeTeam: string; awayTeam: string; enabled?: boolean
}) {
  const { competition } = useAppState()
  const query = useQuery({
    queryKey: ['oddsHistory', competition, matchId],
    queryFn: async () => {
      const params = new URLSearchParams({ competition })
      const response = await fetch(`/api/odds-history/${encodeURIComponent(matchId)}?${params}`)
      if (!response.ok) throw new Error('Quotenverlauf konnte nicht geladen werden.')
      return response.json() as Promise<OddsHistoryData>
    },
    enabled: enabled && Boolean(matchId),
    staleTime: 300_000,
    retry: false,
  })

  if (!enabled) return null
  if (query.isLoading) return <p className="mt-3 text-sm text-fg-2">Quotenverlauf wird geladen…</p>
  if (query.isError || !query.data) return <p className="mt-3 text-sm text-fg-2">Quotenverlauf konnte nicht geladen werden.</p>
  const { observations } = query.data
  if (!observations.length) {
    return <p className="mt-3 text-sm text-fg-2">Für dieses Spiel ist kein gespeicherter Quotenverlauf verfügbar.</p>
  }

  const first = observations[0]
  const latest = observations[observations.length - 1]
  const changes = query.data.probability_change_pp
  const homeChange = changes?.home
  const homeTrend = homeChange === undefined
    ? null
    : homeChange > 0.05
      ? `Die bereinigte Heimsiegchance stieg von ${probability(first.probabilities.home)} auf ${probability(latest.probabilities.home)}.`
      : homeChange < -0.05
        ? `Die bereinigte Heimsiegchance sank von ${probability(first.probabilities.home)} auf ${probability(latest.probabilities.home)}.`
        : `Die bereinigte Heimsiegchance blieb mit ${probability(latest.probabilities.home)} etwa stabil.`

  return (
    <section aria-label="Quotenverlauf" className="mt-4 rounded-xl border border-line bg-surface p-4 text-left">
      <div>
        <h3 className="text-base font-bold text-fg">Quotenverlauf</h3>
        <p className="mt-1 text-xs leading-relaxed text-fg-2">Gespeicherte Buchmacherquoten vor Anpfiff · Wahrscheinlichkeiten ohne Buchmachermarge</p>
      </div>
      {homeTrend ? (
        <div className="mt-3 rounded-lg border border-emerald-a/20 bg-emerald-a/5 px-3 py-2.5">
          <p className="text-sm font-semibold text-fg">{homeTrend} {homeChange !== undefined && <span className="text-emerald-a">({signedPoints(homeChange)})</span>}</p>
          <dl className="mt-2 grid grid-cols-1 gap-1 text-xs text-fg-2 sm:grid-cols-3">
            {OUTCOMES.map(({ key, label }) => (
              <div key={key} className="flex justify-between gap-2 sm:block">
                <dt>{key === 'home' ? homeTeam : key === 'away' ? awayTeam : label}</dt>
                <dd className="font-semibold tabular-nums text-fg-2">{signedPoints(changes![key])}</dd>
              </div>
            ))}
          </dl>
        </div>
      ) : (
        <p className="mt-3 rounded-lg bg-surface-2 px-3 py-2.5 text-sm text-fg-2">Es gibt eine gespeicherte Beobachtung. Eine Veränderung lässt sich damit noch nicht bestimmen.</p>
      )}
      {observations.length >= 2 && <OddsHistoryChart observations={observations} homeTeam={homeTeam} awayTeam={awayTeam} />}
      <ol aria-label="Gespeicherte Quotenpunkte" className="mt-3 space-y-2">
        {observations.map((point) => (
          <li key={point.observed_at} className="rounded-lg bg-surface-2 px-3 py-3">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
              <span className="text-sm font-bold text-fg">{BUCKET_LABEL[point.bucket] ?? point.bucket}</span>
              <span className="text-xs tabular-nums text-fg-2">{observedTime(point.observed_at)} · {point.source === 'odds_api' ? 'The Odds API' : point.source}</span>
            </div>
            <dl className="mt-2 grid grid-cols-3 gap-2 text-center">
              {OUTCOMES.map(({ key, label }) => (
                <div key={key} className="min-w-0 rounded-md border border-line bg-surface px-1.5 py-2">
                  <dt className="truncate text-[11px] font-semibold text-fg-2">{key === 'home' ? homeTeam : key === 'away' ? awayTeam : label}</dt>
                  <dd className="mt-1 text-sm font-bold tabular-nums text-fg">{point.odds[key].toFixed(2)}</dd>
                  <dd className="text-xs tabular-nums text-fg-2">{probability(point.probabilities[key])}</dd>
                </div>
              ))}
            </dl>
          </li>
        ))}
      </ol>
    </section>
  )
}
