import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'

type EditorKeyRequest = { resolve: (token: string | null) => void }

export function EditorKeyDialog() {
  const [request, setRequest] = useState<EditorKeyRequest | null>(null)
  const [value, setValue] = useState('')
  const input = useRef<HTMLInputElement>(null)
  const dialog = useRef<HTMLElement>(null)
  const previousFocus = useRef<HTMLElement | null>(null)

  useEffect(() => {
    const onRequest = (event: Event) => {
      const detail = (event as CustomEvent<EditorKeyRequest>).detail
      previousFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
      setValue('')
      setRequest(detail)
    }
    window.addEventListener('editor-key-required', onRequest)
    return () => window.removeEventListener('editor-key-required', onRequest)
  }, [])

  const finish = useCallback((token: string | null) => {
    if (!request) return
    request.resolve(token)
    setRequest(null)
    setValue('')
    window.requestAnimationFrame(() => {
      // A completed shared-tip save may have moved focus to the next fixture.
      if (document.activeElement === document.body) previousFocus.current?.focus({ preventScroll: true })
    })
  }, [request])

  useEffect(() => {
    if (!request) return
    input.current?.focus()
    const originalOverflow = document.body.style.overflow
    const app = document.getElementById('app-shell-content')
    const wasInert = app?.inert ?? false
    document.body.style.overflow = 'hidden'
    if (app) app.inert = true
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        finish(null)
        return
      }
      if (event.key !== 'Tab') return
      const controls = [...(dialog.current?.querySelectorAll<HTMLElement>('input,button') ?? [])]
        .filter((element) => !element.matches(':disabled'))
      const first = controls[0]
      const last = controls.at(-1)
      if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) {
        event.preventDefault()
        last?.focus()
      } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialog.current)) {
        event.preventDefault()
        first?.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = originalOverflow
      if (app) app.inert = wasInert
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [request, finish])

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    finish(value.trim() || null)
  }

  if (!request) return null
  return <div className="shell-overlay" onClick={() => finish(null)}>
    <section ref={dialog} role="dialog" aria-modal="true" aria-labelledby="editor-key-title" className="shell-menu" onClick={(event) => event.stopPropagation()}>
      <div className="shell-menu-heading">
        <h2 id="editor-key-title">Editor-Schlüssel</h2>
        <button type="button" onClick={() => finish(null)} className="min-h-11 px-3 text-sm text-fg-2 hover:bg-surface-2">Schliessen ×</button>
      </div>
      <form onSubmit={submit} className="mt-4 space-y-3">
        <label className="block text-sm text-fg-2" htmlFor="editor-key-input">Schlüssel zum Speichern gemeinsamer Änderungen eingeben.</label>
        <input ref={input} id="editor-key-input" type="password" autoComplete="current-password" value={value} onChange={(event) => setValue(event.target.value)} className="min-h-11 w-full rounded-lg border border-line-2 bg-surface px-3 text-fg outline-none focus:border-emerald-a focus:ring-2 focus:ring-emerald-a/20" />
        <div className="flex justify-end gap-2">
          <button type="button" onClick={() => finish(null)} className="min-h-11 rounded-lg border border-line-2 px-4 text-sm font-semibold text-fg-2">Abbrechen</button>
          <button type="submit" disabled={!value.trim()} className="min-h-11 rounded-lg bg-action px-4 text-sm font-semibold text-on-action disabled:opacity-50">Weiter</button>
        </div>
      </form>
    </section>
  </div>
}
