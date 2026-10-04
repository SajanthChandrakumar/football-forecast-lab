import { useCallback, useEffect, useState } from 'react'

// Same localStorage key as the legacy frontend so the preference carries over.
const KEY = 'theme'

export function useTheme() {
  const [light, setLight] = useState(() => {
    try { return localStorage.getItem(KEY) !== 'dark' }
    catch { return true }
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', light ? 'light' : 'dark')
    try { localStorage.setItem(KEY, light ? 'light' : 'dark') }
    catch { /* The theme remains usable without browser storage. */ }
  }, [light])

  const toggle = useCallback(() => setLight((v) => !v), [])
  return { light, toggle }
}
