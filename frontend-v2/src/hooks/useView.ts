import { useLocation, useSearchParams } from 'react-router-dom'

export function useView<T extends string>(views: readonly T[], defaultView: T): readonly [T, (next: T) => void] {
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const requested = params.get('view') as T | null
  const view = requested && views.includes(requested) ? requested : defaultView
  const select = (next: T) => {
    if (next === view || !views.includes(next)) return
    setParams(current => {
      const updated = new URLSearchParams(current)
      if (next === defaultView) updated.delete('view')
      else updated.set('view', next)
      return updated
    }, { state: { ...location.state, viewDepth: (location.state?.viewDepth ?? 0) + 1 } })
  }
  return [view, select]
}
