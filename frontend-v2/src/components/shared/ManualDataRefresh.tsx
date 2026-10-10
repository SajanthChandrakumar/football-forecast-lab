import { useEffect, useId, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, ManualRefreshError } from '../../lib/api'
import type { CompetitionId } from '../../lib/types'
import { competitionLabel } from '../../lib/competition.mjs'
import { formatObservedAt } from '../../lib/observed-at.mjs'
import { useAppState } from '../../state/AppState'

const SOURCE_STATUS: Record<string, string> = {
  fresh: 'Neu geladen', stale: 'Veraltet', partial: 'Teilweise',
  failed: 'Abruffehler', unavailable: 'Nicht erfasst',
}
const RESULT_STATUS = { success: 'Aktualisiert', partial: 'Teilweise aktualisiert', failed: 'Abruf fehlgeschlagen' }

export function ManualDataRefresh() {
  const { competition, competitions } = useAppState()
  const inputId = useId()
  const keyInput = useRef<HTMLInputElement>(null)
  const report = useRef<HTMLDivElement>(null)
  const [hasKey, setHasKey] = useState(false)
  const [cooldown, setCooldown] = useState(0)
  const cooldownUntil = useRef(0)
  const startCooldown = (seconds: number) => {
    cooldownUntil.current = Date.now() + seconds * 1000
    setCooldown(seconds)
  }
  const qc = useQueryClient()
  const refresh = useMutation({
    // Only the competition enters TanStack's mutation cache. The key stays transient.
    mutationFn: (requestedCompetition: CompetitionId) => {
      const token = keyInput.current?.value ?? ''
      if (keyInput.current) keyInput.current.value = ''
      setHasKey(false)
      return api.manualRefresh(requestedCompetition, token)
    },
    onSuccess: result => startCooldown(result.cooldown_seconds),
    onError: error => {
      if (error instanceof ManualRefreshError && error.retryAfter) startCooldown(error.retryAfter)
    },
    // A provider can update some sources even when another source fails.
    onSettled: (_data, _error, requestedCompetition) => qc.invalidateQueries({
      predicate: query => query.queryKey[1] === requestedCompetition,
    }),
  })
  useEffect(() => {
    if (!cooldown) return
    const interval = window.setInterval(() => setCooldown(Math.max(0, Math.ceil((cooldownUntil.current - Date.now()) / 1000))), 1000)
    return () => window.clearInterval(interval)
  }, [cooldown])
  useEffect(() => {
    if (keyInput.current) keyInput.current.value = ''
    setHasKey(false)
  }, [competition])
  useEffect(() => {
    if (refresh.data) report.current?.scrollIntoView({ block: 'nearest' })
  }, [refresh.data])
  const supported = competition === 'epl2026' || competition === 'ucl2026'

  return <div className="rounded border border-line px-3 py-3">
    <p className="mb-3 text-xs font-semibold text-fg">API-Daten aktualisieren</p>
    {supported ? <form onSubmit={event => { event.preventDefault(); if (hasKey && !refresh.isPending && !cooldown) refresh.mutate(competition) }}>
      <label htmlFor={inputId} className="block text-xs text-fg-2">Admin-Schlüssel</label>
      <input id={inputId} ref={keyInput} type="password" autoComplete="off" spellCheck={false}
        onChange={event => setHasKey(Boolean(event.target.value))} disabled={refresh.isPending}
        className="mb-2 mt-1 min-h-11 w-full min-w-0 rounded border border-line bg-surface-2 px-2 text-base sm:text-sm text-fg outline-none focus:border-emerald-a" />
      <button type="submit" disabled={!hasKey || refresh.isPending || cooldown > 0}
        className="min-h-11 w-full rounded bg-action px-2 py-2 text-xs font-semibold text-on-action disabled:opacity-50">
        {refresh.isPending ? 'API-Daten werden geladen…' : cooldown ? `Erneut in ${cooldown} s` : 'Aktuelle API-Daten holen'}
      </button>
      <p className="mt-2 text-[11px] leading-relaxed text-fg-3">Anbieter jetzt abrufen. Der Schlüssel wird nicht gespeichert.</p>
    </form> : <p className="text-xs text-fg-3">Sofortabruf für PL und UCL. Wähle oben den Wettbewerb.</p>}
    {refresh.isError && <p role="alert" className="mt-3 text-xs leading-relaxed text-red-a">{refresh.error.message}</p>}
    {refresh.data && <div ref={report} className="mt-3 border-t border-line pt-3" role="status" aria-live="polite">
      <p className="text-xs font-semibold text-fg">{RESULT_STATUS[refresh.data.status]} · {competitionLabel(refresh.data.competition, competitions)}</p>
      <ul className="mt-2 space-y-3">
        {refresh.data.sources.map(source => <li key={source.id} className="text-[11px] leading-relaxed">
          <div className="flex flex-wrap items-baseline justify-between gap-x-2"><span className="font-medium text-fg-2">{source.label}</span><span className={source.status === 'fresh' ? 'text-emerald-a' : 'text-fg-3'}>{SOURCE_STATUS[source.status] ?? 'Nicht erfasst'}</span></div>
          {source.observed_at && <p className="text-fg-3">{formatObservedAt(source.observed_at)}</p>}
          {source.message && <p className="mt-0.5 text-fg-3">{source.message}</p>}
        </li>)}
      </ul>
    </div>}
  </div>
}
