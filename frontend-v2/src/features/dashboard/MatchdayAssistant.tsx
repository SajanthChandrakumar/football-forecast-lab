import { useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { buildAssistantRows, getSaveCandidates, isValidScoreTip, saveTipBatch, TIP_BATCH_LIMIT } from '../../lib/matchday-assistant.mjs'
import { fixtureStatus, sharedTipIsOpen } from '../../lib/fixture-status.mjs'
import { groupFixturesByRound } from '../../lib/fixture-rounds.mjs'
import { kickoffTime, shortDate } from '../../lib/format'
import type { Match } from '../../lib/types'
import { useArchive } from '../../hooks/queries'
import { useAppState } from '../../state/AppState'

type StringMap = Record<string, string>
type RoundStateMap = Record<string, StringMap>
const EMPTY_STRING_MAP: StringMap = {}
const EMPTY_MATCHES: Match[] = []

export function MatchdayAssistant({ matches, now }: { matches: Match[]; now: number }) {
  const { competition } = useAppState()
  const { data: archive, isLoading: archiveLoading, error: archiveError } = useArchive()
  const queryClient = useQueryClient()
  const rounds = useMemo(() => groupFixturesByRound(matches), [matches])
  const selectableRounds = rounds.filter((round) => round.matches.some((match) => {
    const kickoff = Date.parse(match.raw_match?.commence_time ?? '')
    return Number.isFinite(kickoff) && !match.completed && !match.actual_score
  }))
  const defaultRound = selectableRounds.find((round) => round.matches.some((match) =>
    fixtureStatus(match, now) === 'upcoming' && sharedTipIsOpen(match.raw_match?.commence_time, now),
  )) ?? selectableRounds.find((round) => round.firstKickoff > now) ?? selectableRounds[0]
  const [selection, setSelection] = useState<{ competition: string; key: string } | null>(null)
  const selectedRound = selectableRounds.find((round) =>
    selection?.competition === competition && round.key === selection.key,
  ) ?? defaultRound
  const stateKey = selectedRound ? `${competition}:${selectedRound.key}` : ''
  const [draftsByRound, setDraftsByRound] = useState<RoundStateMap>({})
  const [savedByRound, setSavedByRound] = useState<RoundStateMap>({})
  const [errorsByRound, setErrorsByRound] = useState<RoundStateMap>({})
  const [saving, setSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState('')
  const [copyMessage, setCopyMessage] = useState('')
  const drafts = draftsByRound[stateKey] ?? EMPTY_STRING_MAP
  const savedOverrides = savedByRound[stateKey] ?? EMPTY_STRING_MAP
  const rowErrors = errorsByRound[stateKey] ?? EMPTY_STRING_MAP
  const rows = buildAssistantRows(
    selectedRound?.matches ?? EMPTY_MATCHES, archive, drafts, savedOverrides, now,
  )
  const candidates = getSaveCandidates(rows)
  const invalidCount = rows.filter((row) => row.editable && row.changed && row.value && !isValidScoreTip(row.value)).length
  const archiveReady = Boolean(archive) || (!archiveLoading && !archiveError)
  const savedCount = rows.filter((row) => isValidScoreTip(row.savedTip)).length
  const deadline = rows
    .filter((row) => row.status !== 'played')
    .map((row) => row.kickoff - 5 * 60_000)
    .filter((time) => Number.isFinite(time) && time > now)
    .sort((a, b) => a - b)[0]

  if (!selectedRound) return null

  const updateRoundMap = (setter: (update: (state: RoundStateMap) => RoundStateMap) => void, values: StringMap) => {
    setter((state) => ({ ...state, [stateKey]: { ...state[stateKey], ...values } }))
  }

  const saveTips = async () => {
    if (saving || !archiveReady || !candidates.length) return
    setSelection({ competition, key: selectedRound.key })
    setSaving(true)
    setSaveMessage('')
    const { results, remaining } = await saveTipBatch(candidates, async ({ match, tip }) => {
      const currentTime = Date.now()
      if (fixtureStatus(match, currentTime) !== 'upcoming' || !sharedTipIsOpen(match.raw_match?.commence_time, currentTime)) {
        throw new Error('Tippabgabe ist laut Server bereits geschlossen (T-5).')
      }
      await api.saveUserTip(competition, match.id, tip)
    })
    const saved: StringMap = {}
    const newDrafts: StringMap = {}
    const failures: StringMap = {}
    let successCount = 0
    let failureCount = 0
    for (const result of results) {
      const { match, tip } = result.item
      if (result.ok) {
        saved[match.id] = tip
        newDrafts[match.id] = tip
        successCount += 1
      } else {
        failures[match.id] = result.error.includes('T-5') || result.error.includes('409')
          ? 'Tippabgabe wurde kurz vor dem Speichern geschlossen (T-5).'
          : 'Speichern fehlgeschlagen. Bitte erneut versuchen.'
        failureCount += 1
      }
    }
    if (successCount) {
      updateRoundMap(setSavedByRound, saved)
      updateRoundMap(setDraftsByRound, newDrafts)
    }
    setErrorsByRound((state) => {
      const nextErrors = { ...state[stateKey] }
      for (const result of results) if (result.ok) delete nextErrors[result.item.match.id]
      Object.assign(nextErrors, failures)
      return { ...state, [stateKey]: nextErrors }
    })
    let refreshFailed = false
    try {
      await queryClient.invalidateQueries({ queryKey: ['archive', competition] })
    } catch {
      refreshFailed = true
    }
    setSaveMessage(`${successCount} gespeichert${failureCount ? ` · ${failureCount} fehlgeschlagen` : ''}${remaining ? ` · ${remaining} weitere im nächsten Schritt` : ''}${refreshFailed ? ' · Anzeige konnte nicht aktualisiert werden' : ''}.`)
    setSaving(false)
  }

  const copyCard = async () => {
    const text = [
      `${selectedRound.label} · Tippkarte`,
      ...rows.map(({ match, value }) => `${match.home_disp || match.home_team} – ${match.away_disp || match.away_team}: ${value || '–'}`),
    ].join('\n')
    try {
      if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable')
      await navigator.clipboard.writeText(text)
      setCopyMessage('Die angezeigte Tippkarte wurde kopiert.')
    } catch {
      setCopyMessage('Kopieren ist in diesem Browser nicht verfügbar. Bitte Tippkarte markieren und kopieren.')
    }
  }

  return (
    <section className="glass mb-7 overflow-hidden" aria-labelledby="matchday-assistant-title">
      <div className="border-b border-line bg-[linear-gradient(135deg,var(--surface),var(--surface-2))] p-4 sm:p-5">
        <p className="kicker">Tipps für die ganze Runde</p>
        <div className="mt-1 flex flex-wrap items-center justify-between gap-3">
          <h2 id="matchday-assistant-title" className="text-lg font-semibold text-fg">Spieltag-Assistent</h2>
          <label className="flex min-h-11 items-center gap-2 text-sm font-semibold text-fg-2">
            <span className="sr-only">Spielwoche oder Runde auswählen</span>
            <select
              value={selectedRound.key}
              disabled={saving}
              onChange={(event) => {
                setSelection({ competition, key: event.target.value })
                setSaveMessage('')
                setCopyMessage('')
              }}
              className="max-w-[15rem] rounded-xl border border-line-2 bg-surface px-3 py-2 text-sm font-bold text-fg"
            >
              {selectableRounds.map((round) => <option key={round.key} value={round.key}>{round.label} · {round.matches.length} Spiele</option>)}
            </select>
          </label>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-fg-2">
          <span className="font-semibold">{archiveReady ? `${savedCount}/${rows.length} Tipps gespeichert` : 'Gespeicherte Tipps werden geladen'}</span>
          {deadline
            ? <span>Nächste T-5-Frist: {shortDate(new Date(deadline).toISOString())} · {kickoffTime(new Date(deadline).toISOString())}</span>
            : <span>Keine weitere T-5-Frist in dieser Runde.</span>}
        </div>
        <p className="mt-2 text-xs text-fg-3">Gemeinsam · Für alle sichtbar</p>
      </div>

      <details className="group">
        <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 font-bold text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-a sm:px-5 [&::-webkit-details-marker]:hidden">
          <span>Tipps bearbeiten <span className="ml-1 text-sm font-semibold text-fg-3">({rows.length} Spiele)</span></span>
          <span aria-hidden="true" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#193b2b] text-lg text-[#f8f7f2] transition-transform group-open:rotate-180">⌄</span>
        </summary>
        <div className="border-t border-line p-3 sm:p-4">
          <ul className="space-y-2">
            {rows.map((row) => {
              const { match } = row
              const error = rowErrors[match.id]
              const invalid = Boolean(row.value) && !isValidScoreTip(row.value)
              const statusLabel = row.saved ? 'Gespeichert' : row.touched && row.value ? 'Dein Entwurf' : row.value ? 'Vorschlag' : 'Tipp fehlt'
              const kickoff = Number.isFinite(row.kickoff)
                ? `${shortDate(new Date(row.kickoff).toISOString())} · ${kickoffTime(match.raw_match?.commence_time)}`
                : 'Anstoß offen'
              return (
                <li key={match.id} className="rounded-xl border border-line bg-surface-2 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                    <span className="min-w-0 flex-1 text-sm font-bold leading-snug text-fg">{match.home_disp || match.home_team} – {match.away_disp || match.away_team}</span>
                    <span className="shrink-0 text-xs font-semibold text-fg-3">{kickoff}</span>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                    {row.status === 'played' ? (
                      <span className="display-num min-w-20 rounded-lg border border-line bg-surface px-3 py-2 text-center text-lg font-bold text-fg">{row.value || '–'}</span>
                    ) : (
                      <label className="flex min-h-11 min-w-0 flex-1 items-center gap-2">
                        <span className="sr-only">Tipp für {match.home_team} gegen {match.away_team}</span>
                        <input
                          type="text"
                          inputMode="text"
                          autoComplete="off"
                          maxLength={5}
                          value={row.value}
                          readOnly={!row.editable || saving}
                          onChange={(event) => {
                            setSelection({ competition, key: selectedRound.key })
                            updateRoundMap(setDraftsByRound, { [match.id]: event.target.value })
                            setErrorsByRound((state) => {
                              const next = { ...state[stateKey] }
                              delete next[match.id]
                              return { ...state, [stateKey]: next }
                            })
                            setSaveMessage('')
                          }}
                          placeholder="z. B. 2:1"
                          aria-invalid={invalid}
                          className="min-h-11 w-24 rounded-lg border border-line-2 bg-surface px-3 text-center font-mono text-lg font-bold text-fg outline-none focus:border-emerald-a focus:ring-2 focus:ring-emerald-a/20 read-only:opacity-75"
                        />
                        <span className="text-xs font-semibold text-fg-3">{row.status === 'pending' ? 'Anstoß vorbei' : !row.editable ? 'Abgabe geschlossen (T-5)' : ''}</span>
                      </label>
                    )}
                    <span className={`rounded-full border px-2.5 py-1 text-xs font-bold ${row.saved ? 'border-emerald-a/30 bg-emerald-dim text-emerald-a' : 'border-line text-fg-2'}`}>
                      {row.status === 'played' ? (row.saved ? 'Gespeichert' : 'Gespielt') : statusLabel}
                    </span>
                  </div>
                  {row.suggestion && <p className="mt-2 text-xs text-fg-3">
                    Vorschlag: {row.sourceLabel}
                    {row.observedAt && <> · Datenstand {shortDate(row.observedAt)} {kickoffTime(row.observedAt)}</>}
                    {row.stale && <> · Stand möglicherweise veraltet</>}
                  </p>}
                  {invalid && row.editable && <p className="mt-2 text-xs font-semibold text-red-a">Bitte Heim:Auswärts im Format 0:0 bis 20:20 eingeben.</p>}
                  {row.status !== 'played' && !row.value && row.editable && <p className="mt-2 text-xs text-fg-3">Kein gültiger Vorschlag vorhanden. Tipp manuell eingeben.</p>}
                  {error && <p role="alert" className="mt-2 text-xs font-semibold text-red-a">{error}</p>}
                </li>
              )
            })}
          </ul>

          <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
            <button type="button" onClick={saveTips} disabled={saving || !archiveReady || !candidates.length} className="min-h-11 rounded-xl bg-emerald-a px-4 py-2 text-sm font-bold text-white transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50">
              {saving ? 'Speichert …' : candidates.length ? `${Math.min(candidates.length, TIP_BATCH_LIMIT)} Tipp${Math.min(candidates.length, TIP_BATCH_LIMIT) === 1 ? '' : 's'} speichern` : 'Keine gültigen Änderungen'}
            </button>
            <button type="button" onClick={copyCard} className="min-h-11 rounded-xl border border-emerald-a/40 bg-emerald-dim px-4 py-2 text-sm font-bold text-emerald-a">Tippkarte kopieren</button>
          </div>
          {!archiveReady && <p role="status" className="mt-2 text-sm text-amber-a">Gespeicherte Tipps konnten nicht geladen werden. Speichern ist pausiert, damit vorhandene Tipps nicht überschrieben werden.</p>}
          {invalidCount > 0 && <p className="mt-2 text-sm text-fg-2">{invalidCount} ungültige {invalidCount === 1 ? 'Eingabe' : 'Eingaben'} werden nicht gespeichert.</p>}
          {saveMessage && <p role="status" className="mt-2 text-sm font-semibold text-fg-2">{saveMessage}</p>}
          {copyMessage && <p role="status" className="mt-2 text-sm text-fg-2">{copyMessage}</p>}
        </div>
      </details>
    </section>
  )
}
