import { useCallback, useEffect, useState } from 'react'

// Same localStorage key as the legacy frontend so the preference carries over.
const KEY = 'theme'

export function useTheme() {
  const [light, setLight] = useState(() => localStorage.getItem(KEY) !== 'dark')

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', light ? 'light' : 'dark')
    localStorage.setItem(KEY, light ? 'light' : 'dark')
  }, [light])

  const toggle = useCallback(() => setLight((v) => !v), [])
  return { light, toggle }
}
