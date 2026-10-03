import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useSaveUserTip } from '../../hooks/queries'
import { fixtureStatus, sharedTipIsOpen } from '../../lib/fixture-status.mjs'
import { formatScoreFields, parseScoreFields } from '../../lib/score-tip.mjs'
import type { CompetitionId, Match } from '../../lib/types'

type Props = {
  match: Match
  competition: CompetitionId
  savedTip?: string | null
  now: number
  compact?: boolean
  autoFocus?: boolean
  onAutoFocus?: () => void
  onSaveAndNext?: () => void
  onSaveStart?: () => void
  onSaved?: (tip: string) => void
}

type Feedback = { kind: 'pending' | 'success' | 'error'; text: string }
const EMPTY_SCORE = { home: '', away: '' }

function tipErrorMessage(error: unknown) {
  const message = error instanceof Error ? error.message : ''
  if (message.startsWith('409')) return 'Die gemeinsame Tippabgabe ist fünf Minuten vor Anpfiff geschlossen.'
  if (message.startsWith('404')) return 'Dieses Spiel ist nicht im Tipp-Archiv gespeichert.'
  return 'Der Tipp konnte nicht gespeichert werden. Bitte prüfe die Verbindung und versuche es erneut.'
}

export function SharedTipEditor({ match, competition, savedTip, now, compact = false, autoFocus = false, onAutoFocus, onSaveAndNext, onSaveStart, onSaved }: Props) {
  const saveTip = useSaveUserTip()
  const kickoff = match.raw_match?.commence_time
  const [score, setScore] = useState(() => parseScoreFields(savedTip ?? '') ?? EMPTY_SCORE)
  const [confirmedTip, setConfirmedTip] = useState(savedTip ?? null)
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  const [cutoffReached, setCutoffReached] = useState(() => fixtureStatus(match, Date.now()) === 'upcoming' && !sharedTipIsOpen(kickoff, Date.now()))
  const editRevision = useRef(0)
  const homeField = useRef<HTMLInputElement>(null)
  const didAutoFocus = useRef(false)
  const state = fixtureStatus(match, now)
  const canSave = state === 'upcoming' && sharedTipIsOpen(kickoff, now) && !cutoffReached
  const scoreForSave = formatScoreFields(score.home, score.away)

  useEffect(() => {
    if (savedTip?.trim()) {
      setConfirmedTip(savedTip)
      if (editRevision.current === 0) setScore(parseScoreFields(savedTip) ?? EMPTY_SCORE)
    } else if (editRevision.current === 0) {
      setScore(EMPTY_SCORE)
    }
  }, [savedTip])

  useEffect(() => {
    if (!autoFocus || didAutoFocus.current) return
    homeField.current?.focus()
    didAutoFocus.current = true
    onAutoFocus?.()
  }, [autoFocus, onAutoFocus])

  useEffect(() => {
    const cutoff = Date.parse(kickoff ?? '') - 5 * 60_000
    if (!Number.isFinite(cutoff)) return
    const delay = cutoff - Date.now()
    if (delay <= 0) {
      setCutoffReached(true)
      return
    }
    const timer = window.setTimeout(() => setCutoffReached(true), delay)
    return () => window.clearTimeout(timer)
  }, [kickoff])

  const updateScore = (side: 'home' | 'away', value: string) => {
    editRevision.current += 1
    setScore((current) => ({ ...current, [side]: value }))
    setFeedback(null)
  }

  const save = (goNext = false) => {
    if (!scoreForSave) {
      setFeedback({ kind: 'error', text: 'Bitte gib für beide Teams eine ganze, nicht negative Torzahl ein.' })
      return
    }

    if (state !== 'upcoming' || !sharedTipIsOpen(kickoff, Date.now())) {
      setCutoffReached(true)
      setFeedback({ kind: 'error', text: kickoff && Number.isFinite(Date.parse(kickoff))
        ? 'Die gemeinsame Tippabgabe ist fünf Minuten vor Anpfiff geschlossen.'
        : 'Ohne Anstoßzeit kann kein gemeinsamer Tipp gespeichert werden.' })
      return
    }

    const revisionAtSubmit = editRevision.current
    const submittedTip = scoreForSave
    onSaveStart?.()
    setFeedback({ kind: 'pending', text: 'Der gemeinsame Tipp wird gespeichert …' })
    saveTip.mutate({ matchId: match.id, tip: submittedTip, targetCompetition: competition }, {
      onSuccess: () => {
        setConfirmedTip(submittedTip)
        if (editRevision.current === revisionAtSubmit) {
          setScore(parseScoreFields(submittedTip) ?? EMPTY_SCORE)
          editRevision.current = 0
        }
        setFeedback({ kind: 'success', text: `Gemeinsamer Spieltipp ${submittedTip} gespeichert.` })
        onSaved?.(submittedTip)
        if (goNext) onSaveAndNext?.()
      },
      onError: (error) => setFeedback({ kind: 'error', text: tipErrorMessage(error) }),
    })
  }

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    save()
  }

  const cutoffMessage = state === 'upcoming'
    ? kickoff && Number.isFinite(Date.parse(kickoff))
      ? 'Speichern ist fünf Minuten vor Anpfiff gesperrt.'
      : 'Speichern ist gesperrt, weil die Anstoßzeit fehlt.'
    : 'Die gemeinsame Tippabgabe ist geschlossen.'

  return (
    <section className={compact ? 'rounded-lg border border-line bg-surface-2 p-3' : 'rounded-lg border border-line p-4'}>
      <h3 className="text-sm font-semibold text-fg">Gemeinsamen Ergebnistipp speichern</h3>
      {!compact && <p className="mt-1 text-xs leading-relaxed text-fg-2">Dieser Tipp wird zentral für das Spiel gespeichert. Die Abgabe schließt fünf Minuten vor Anpfiff.</p>}
      {confirmedTip && <p className="mt-2 text-xs text-fg-2">Gespeicherter gemeinsamer Tipp: <strong className="tabular-nums text-fg">{confirmedTip}</strong></p>}
      <form onSubmit={submit} className={compact ? 'mt-2 grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] items-end gap-2' : 'mt-3 grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-end gap-2'}>
        <label className="min-w-0 text-xs font-medium text-fg-2">
          <span className="block truncate">{compact ? 'Heim' : `Tore ${match.home_team}`}</span>
          <input ref={homeField} required aria-label={`Tore ${match.home_team}`} type="number" min={0} step={1} inputMode="numeric" value={score.home} onChange={(event) => updateScore('home', event.target.value)} readOnly={!canSave || saveTip.isPending} className="mt-1 min-h-11 w-full min-w-0 rounded-lg border border-line-2 bg-surface px-2 text-center text-base tabular-nums text-fg outline-none focus:border-blue-a focus:ring-2 focus:ring-blue-a/20 read-only:text-fg-2" />
        </label>
        {!compact && <span className="pb-2 text-sm text-fg-3">:</span>}
        <label className="min-w-0 text-xs font-medium text-fg-2">
          <span className="block truncate">{compact ? 'Auswärts' : `Tore ${match.away_team}`}</span>
          <input required aria-label={`Tore ${match.away_team}`} type="number" min={0} step={1} inputMode="numeric" value={score.away} onChange={(event) => updateScore('away', event.target.value)} readOnly={!canSave || saveTip.isPending} className="mt-1 min-h-11 w-full min-w-0 rounded-lg border border-line-2 bg-surface px-2 text-center text-base tabular-nums text-fg outline-none focus:border-blue-a focus:ring-2 focus:ring-blue-a/20 read-only:text-fg-2" />
        </label>
        <button type="submit" disabled={!canSave || saveTip.isPending} className={compact ? 'min-h-11 rounded-lg bg-action px-3 text-sm font-semibold text-on-action hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50' : 'col-span-3 min-h-11 w-full rounded-lg border border-blue-a/40 bg-blue-a/10 px-4 text-sm font-semibold text-blue-a hover:bg-blue-a/15 disabled:cursor-not-allowed disabled:opacity-50'}>
          {saveTip.isPending ? 'Speichert …' : compact ? 'Speichern' : 'Gemeinsamen Spieltipp speichern'}
        </button>
        {compact && onSaveAndNext && <button type="button" disabled={!canSave || saveTip.isPending} onClick={() => save(true)} className="col-span-3 min-h-11 rounded-lg border border-line-2 px-3 text-sm font-semibold text-fg hover:bg-surface disabled:cursor-not-allowed disabled:opacity-50">
          Speichern & nächstes Spiel
        </button>}
      </form>
      {!canSave && <p className="mt-2 text-xs text-fg-2">{cutoffReached ? 'Die Tippabgabe wurde geschlossen.' : cutoffMessage}</p>}
      {feedback && <p className="mt-2 text-xs text-fg-2" role={feedback.kind === 'error' ? 'alert' : 'status'}>{feedback.text}</p>}
    </section>
  )
}
