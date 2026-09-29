import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Match } from '../../lib/types'
import { buildMatchdayRadar, type RadarCategory } from '../../lib/matchRadar'
import { dayHeading, kickoffTime } from '../../lib/format'
import { cn } from '../../lib/util'
import { TeamLabel, TipBadge } from '../../components/shared/Badges'

const categories: { key: RadarCategory; label: string; short: string }[] = [
  { key: 'safe', label: 'Klare Tipps', short: 'Klar' },
  { key: 'open', label: 'Offene Spiele', short: 'Offen' },
  { key: 'surprise', label: 'Überraschungsalarm', short: 'Alarm' },
]

const categoryStyle: Record<RadarCategory, string> = {
  safe: 'border-blue-a/35 bg-blue-a/10 text-blue-a',
  open: 'border-line-2 bg-surface-2 text-fg-2',
  surprise: 'border-orange-a/35 bg-orange-a/10 text-orange-a',
}

export function MatchdayRadar({ matches }: { matches: Match[] }) {
  const navigate = useNavigate()
  const radar = useMemo(() => buildMatchdayRadar(matches), [matches])
  const [selected, setSelected] = useState<RadarCategory | null>(null)
  const [showTipCard, setShowTipCard] = useState(false)
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle')

  if (!radar.matches.length) return null

  const fallback = radar.counts.surprise ? 'surprise' : radar.counts.safe ? 'safe' : 'open'
  const active = selected && radar.counts[selected] ? selected : fallback
  const visible = radar.matches.filter((item) => item.category === active)
  const firstTime = radar.matches[0].match.raw_match?.commence_time

  const copyTipCard = async () => {
    try {
      await navigator.clipboard.writeText(radar.tipCard)
      setCopyState('copied')
    } catch {
      setCopyState('failed')
    }
  }

  return (
    <section className="glass mb-7 overflow-hidden" aria-labelledby="matchday-radar-title">
      <div className="border-b border-line bg-[linear-gradient(135deg,var(--surface),var(--surface-2))] p-4 sm:p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="kicker">Nächster Spieltag</p>
            <h2 id="matchday-radar-title" className="mt-1 font-display text-3xl font-black uppercase tracking-wide text-fg">Spieltag-Radar</h2>
            {firstTime && <p className="mt-1 text-sm font-semibold text-fg-2">{dayHeading(String(firstTime))}</p>}
          </div>
          <button type="button" onClick={() => { setShowTipCard((open) => !open); setCopyState('idle') }} aria-expanded={showTipCard} aria-controls="matchday-tip-card" className="min-h-11 shrink-0 rounded-xl bg-emerald-a px-3 text-sm font-bold text-white transition hover:brightness-110">Tippkarte</button>
        </div>
        <p className="mt-4 text-base font-semibold text-fg">{radar.counts.safe} klar · {radar.counts.open} offen · {radar.counts.surprise} Alarm</p>
      </div>

      <div className="p-4 sm:p-5">
        <div className="grid grid-cols-3 gap-2" role="group" aria-label="Radar-Kategorie">
          {categories.map((category) => (
            <button key={category.key} type="button" onClick={() => setSelected(category.key)} disabled={!radar.counts[category.key]} aria-pressed={active === category.key} className={cn('min-h-14 rounded-xl border px-2 py-2 text-center transition disabled:cursor-not-allowed disabled:opacity-50', active === category.key ? categoryStyle[category.key] : 'border-line bg-surface text-fg-3 hover:bg-surface-2')}>
              <span className="block text-lg font-black tabular-nums">{radar.counts[category.key]}</span>
              <span className="block text-[11px] font-bold sm:hidden">{category.short}</span>
              <span className="hidden text-xs font-bold sm:block">{category.label}</span>
            </button>
          ))}
        </div>

        <div className="mt-4 space-y-2">
          {visible.slice(0, 4).map(({ match, reason }) => (
            <button key={match.id} type="button" onClick={() => navigate(`/match/${match.id}`)} className="w-full rounded-xl border border-line bg-surface-2 p-3 text-left transition hover:border-emerald-a/40">
              <span className="flex items-center justify-between gap-3 text-xs font-bold text-fg-3">{kickoffTime(match.raw_match?.commence_time)}<TipBadge tip={match.top_tip} highlight /></span>
              <span className="mt-2 flex items-center gap-2">
                <TeamLabel name={match.home_team} disp={match.home_disp} logo={match.home_logo} className="min-w-0 flex-1" />
                <span className="text-xs font-bold text-fg-3">vs.</span>
                <TeamLabel name={match.away_team} disp={match.away_disp} logo={match.away_logo} className="min-w-0 flex-1 justify-end" />
              </span>
              <span className="mt-2 block text-sm leading-snug text-fg-2">{reason}</span>
            </button>
          ))}
          {visible.length > 4 && <p className="pt-1 text-center text-sm font-semibold text-fg-3">+ {visible.length - 4} weitere im Spielplan</p>}
        </div>

        {showTipCard && (
          <div id="matchday-tip-card" className="mt-4 rounded-xl border border-line-2 bg-surface-2 p-3">
            <div className="flex items-center justify-between gap-3">
              <h3 className="font-bold text-fg">Komplette Tippkarte</h3>
              <button type="button" onClick={copyTipCard} className="min-h-11 rounded-lg border border-emerald-a/40 bg-emerald-dim px-3 text-sm font-bold text-emerald-a">{copyState === 'copied' ? 'Kopiert ✓' : copyState === 'failed' ? 'Kopieren fehlgeschlagen' : 'Kopieren'}</button>
            </div>
            <ul className="mt-3 divide-y divide-line text-sm">
              {radar.matches.map(({ match }) => (
                <li key={match.id} className="flex items-center justify-between gap-3 py-2 first:pt-0 last:pb-0">
                  <span className="min-w-0 truncate text-fg-2">{match.home_disp || match.home_team} – {match.away_disp || match.away_team}</span>
                  <TipBadge tip={match.top_tip} />
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  )
}
