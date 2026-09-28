import { useState, useMemo } from 'react'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { useMatches } from '../../hooks/queries'
import { flag, cn } from '../../lib/util'
import { shortDate } from '../../lib/format'
import { PageTransition, PageHeader, staggerContainer, staggerItem } from '../../components/shared/PageTransition'
import { CardGridSkeleton } from '../../components/shared/Skeleton'
import type { Match } from '../../lib/types'

type EdgeGrade = 'hit' | 'miss' | 'close'

interface GradedEdgeMatch {
  match: Match
  edgePp: number
  absEdge: number
  favHome: boolean
  favTeam: string
  grade?: EdgeGrade
}

function gradeEdge(m: Match, edgePp: number): EdgeGrade | undefined {
  if (!m.actual_score) return undefined
  const parts = m.actual_score.split(':')
  if (parts.length !== 2) return undefined
  const hg = parseInt(parts[0], 10)
  const ag = parseInt(parts[1], 10)
  if (isNaN(hg) || isNaN(ag)) return undefined

  if (Math.abs(edgePp) < 2.0 || hg === ag) {
    return 'close'
  }

  const eloFavoredHome = edgePp > 0
  const homeWon = hg > ag

  return eloFavoredHome === homeWon ? 'hit' : 'miss'
}

export function EdgeView() {
  const { data: matches, isLoading } = useMatches()
  const navigate = useNavigate()
  const [tab, setTab] = useState<'upcoming' | 'history'>('upcoming')

  const { upcoming, historical, stats } = useMemo(() => {
    const now = Date.now()
    const up: GradedEdgeMatch[] = []
    const hist: GradedEdgeMatch[] = []

    for (const m of matches ?? []) {
      if (m.edge_home == null) continue
      const edgePp = m.edge_home * 100
      const absEdge = Math.abs(edgePp)
      const favHome = edgePp > 0
      const favTeam = favHome ? m.home_team : m.away_team

      const isCompleted = m.completed || (m.actual_score != null && m.actual_score !== '')
      if (isCompleted) {
        const grade = gradeEdge(m, edgePp)
        hist.push({ match: m, edgePp, absEdge, favHome, favTeam, grade })
      } else {
        const ct = m.raw_match?.commence_time
        if (ct && new Date(String(ct)).getTime() > now) {
          up.push({ match: m, edgePp, absEdge, favHome, favTeam })
        } else if (m.actual_score) {
          const grade = gradeEdge(m, edgePp)
          hist.push({ match: m, edgePp, absEdge, favHome, favTeam, grade })
        } else {
          up.push({ match: m, edgePp, absEdge, favHome, favTeam })
        }
      }
    }

    up.sort((a, b) => b.absEdge - a.absEdge)
    hist.sort((a, b) => b.absEdge - a.absEdge)

    let hits = 0
    let misses = 0
    let closes = 0
    for (const item of hist) {
      if (item.grade === 'hit') hits++
      else if (item.grade === 'miss') misses++
      else if (item.grade === 'close') closes++
    }
    const decisive = hits + misses
    const hitRate = decisive > 0 ? (hits / decisive) * 100 : 0

    return {
      upcoming: up,
      historical: hist,
      stats: { total: hist.length, hits, misses, closes, hitRate },
    }
  }, [matches])

  const activeCards = tab === 'upcoming' ? upcoming : historical

  return (
    <PageTransition>
      <PageHeader
        title="Modellvergleich"
        subtitle="Wo das Elo-Modell den Buchmachern am stärksten widerspricht — inkl. historischer Trefferbilanz"
      />

      {/* Tabs */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div className="flex rounded-xl bg-surface-2 p-1">
          <button
            type="button"
            onClick={() => setTab('upcoming')}
            className={cn(
              'rounded-lg px-4 py-2 text-xs font-bold transition-all',
              tab === 'upcoming'
                ? 'bg-surface text-fg shadow-sm'
                : 'text-fg-3 hover:text-fg'
            )}
          >
            Kommende Edges ({upcoming.length})
          </button>
          <button
            type="button"
            onClick={() => setTab('history')}
            className={cn(
              'rounded-lg px-4 py-2 text-xs font-bold transition-all',
              tab === 'history'
                ? 'bg-surface text-fg shadow-sm'
                : 'text-fg-3 hover:text-fg'
            )}
          >
            Historie & Trefferbilanz ({historical.length})
          </button>
        </div>

        {tab === 'history' && historical.length > 0 && (
          <div className="flex flex-wrap items-center gap-3 text-xs">
            <div className="glass rounded-lg px-3 py-1.5 font-semibold text-fg">
              Trefferquote:{' '}
              <span className="display-num text-emerald-a font-bold">
                {stats.hitRate.toFixed(0)}%
              </span>
            </div>
            <div className="flex items-center gap-2 rounded-lg bg-surface-2 px-3 py-1.5 font-medium text-fg-2">
              <span className="text-emerald-a font-bold">🎯 {stats.hits} Treffer</span>
              <span>·</span>
              <span className="text-amber-a font-bold">⚖️ {stats.closes} Remis/Knapp</span>
              <span>·</span>
              <span className="text-red-400 font-bold">❌ {stats.misses} Verfehlt</span>
            </div>
          </div>
        )}
      </div>

      {isLoading && <CardGridSkeleton count={4} />}

      {!isLoading && activeCards.length === 0 && (
        <div className="glass rounded-xl p-8 text-center text-fg-2">
          {tab === 'upcoming' ? (
            <p>
              Keine kommenden Spiele mit Edge-Daten.{' '}
              {historical.length > 0 && (
                <button
                  type="button"
                  onClick={() => setTab('history')}
                  className="mt-2 block w-full text-emerald-a underline hover:text-emerald"
                >
                  Wechsle zur Historie ({historical.length} ausgerechnete Spiele) →
                </button>
              )}
            </p>
          ) : (
            <p>Noch keine beendeten Spiele für eine Trefferanalyse vorhanden.</p>
          )}
        </div>
      )}

      <motion.div
        key={tab}
        variants={staggerContainer}
        initial="initial"
        animate="animate"
        className="grid gap-4 md:grid-cols-2"
      >
        {activeCards.map(({ match: m, edgePp, absEdge, favTeam, grade }) => {
          const strength =
            absEdge >= 12
              ? 'text-emerald-a'
              : absEdge >= 6
                ? 'text-amber-a'
                : 'text-fg-3'
          const market = (m.market_home_share ?? 0.5) * 100
          const elo = (m.elo_home_share ?? 0.5) * 100

          return (
            <motion.button
              key={m.id}
              variants={staggerItem}
              onClick={() => navigate(`/match/${m.id}`)}
              className="glass glass-hover p-5 text-left"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-semibold text-fg">
                    {flag(m.home_team)} {m.home_team}{' '}
                    <span className="text-fg-3">vs</span> {flag(m.away_team)}{' '}
                    {m.away_team}
                  </div>
                  <div className="mt-0.5 text-xs text-fg-3">
                    {shortDate(String(m.raw_match?.commence_time))}
                  </div>
                </div>

                <div className="flex flex-col items-end gap-1">
                  <div className={cn('display-num text-2xl', strength)}>
                    {edgePp > 0 ? '+' : ''}
                    {edgePp.toFixed(1)}
                    <span className="ml-0.5 text-xs font-semibold">pp</span>
                  </div>

                  {grade && (
                    <GradeBadge grade={grade} actualScore={m.actual_score} />
                  )}
                </div>
              </div>

              <div className="mt-3 text-xs font-semibold text-fg-2">
                Modell favorisierte <b className="text-fg">{favTeam}</b> stärker
                als der Markt
              </div>

              <div className="mt-3 space-y-2">
                <Bar label="Markt" value={market} color="var(--text-3)" />
                <Bar label="Elo" value={elo} color="var(--emerald)" />
              </div>
            </motion.button>
          )
        })}
      </motion.div>
    </PageTransition>
  )
}

function GradeBadge({
  grade,
  actualScore,
}: {
  grade: EdgeGrade
  actualScore?: string | null
}) {
  if (grade === 'hit') {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/15 px-2 py-0.5 text-[11px] font-bold text-emerald-a">
        🎯 Treffer {actualScore ? `(${actualScore})` : ''}
      </span>
    )
  }
  if (grade === 'miss') {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-red-500/15 px-2 py-0.5 text-[11px] font-bold text-red-400">
        ❌ Verfehlt {actualScore ? `(${actualScore})` : ''}
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-amber-500/15 px-2 py-0.5 text-[11px] font-bold text-amber-a">
      ⚖️ Remis/Knapp {actualScore ? `(${actualScore})` : ''}
    </span>
  )
}

function Bar({
  label,
  value,
  color,
}: {
  label: string
  value: number
  color: string
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-12 text-[10px] font-bold uppercase tracking-wider text-fg-3">
        {label}
      </span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
        <div
          className="h-full rounded-full"
          style={{ width: `${value}%`, background: color }}
        />
      </div>
      <span className="w-10 text-right text-xs tabular-nums text-fg-2">
        {value.toFixed(0)}%
      </span>
    </div>
  )
}
