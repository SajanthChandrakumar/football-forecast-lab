export function formatObservedAt(value, now = Date.now()) {
  const timestamp = Date.parse(value ?? '')
  if (!Number.isFinite(timestamp)) return 'Zeitpunkt nicht verfügbar'

  const ageMinutes = Math.floor(Math.max(0, now - timestamp) / 60_000)
  let age
  if (ageMinutes < 1) age = 'gerade eben'
  else if (ageMinutes < 60) age = `vor ${ageMinutes} Min.`
  else if (ageMinutes < 1_440) age = `vor ${Math.floor(ageMinutes / 60)} Std.`
  else {
    const days = Math.floor(ageMinutes / 1_440)
    age = `vor ${days} ${days === 1 ? 'Tag' : 'Tagen'}`
  }

  const observed = new Intl.DateTimeFormat('de-CH', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
    timeZone: 'Europe/Zurich',
  }).format(timestamp)
  return `Stand ${observed} · ${age}`
}
