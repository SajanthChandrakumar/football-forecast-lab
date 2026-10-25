import { test, expect, NOW } from './fixtures'
import type { Page } from '@playwright/test'

async function settings(page: Page) {
  const mobile = (page.viewportSize()?.width ?? 1440) < 1024
  await page.getByRole('button', { name: mobile ? 'Mehr' : 'Einstellungen', exact: true }).click()
  const dialog = page.getByRole('dialog')
  if (mobile) await dialog.getByRole('navigation', { name: 'Analysen', exact: true }).getByRole('link', { name: /^API & Daten/ }).click()
  else await dialog.getByRole('link', { name: /API & Daten · Quellen und Aktualisierung/ }).click()
  await expect(page.getByRole('heading', { name: 'API & Daten', exact: true })).toBeVisible()
}
const key = (page: Page) => page.getByLabel('Admin-Schlüssel', { exact: true }).filter({ visible: true })
const button = (page: Page) => page.getByRole('button', { name: 'Aktuelle API-Daten holen', exact: true }).filter({ visible: true })
const result = { competition: 'ucl2026', status: 'partial', requested_at: NOW.toISOString(), cooldown_seconds: 60, sources: [
  { id: 'fixtures', label: 'Spiele & Ergebnisse', status: 'fresh', observed_at: NOW.toISOString() },
  { id: 'odds', label: 'Buchmacherquoten', status: 'fresh', observed_at: NOW.toISOString() },
  { id: 'elo', label: 'Elo-Werte', status: 'stale', observed_at: '2026-10-01T19:56:00Z', message: 'Abruf fehlgeschlagen; letzter gespeicherter Stand bleibt erhalten.' },
  { id: 'lineups', label: 'Aufstellungen', status: 'unavailable', observed_at: null, message: '0 von 1 geprüften Spielen mit vollständiger Aufstellung.' },
] }

test('admin refresh authenticates, clears the key, updates data and reports partial success', async ({ page, api }, testInfo) => {
  const calls: string[] = []
  await page.route('**/api/internal/manual-refresh?*', async route => {
    const token = route.request().headers().authorization
    calls.push(token)
    if (token !== 'Bearer test-admin-key') return route.fulfill({ status: 401, json: { detail: 'Admin-Schlüssel ist ungültig.' } })
    api.matches.ucl2026[0].top_tip = api.matches.ucl2026[0].model_tip = '3:1'
    return route.fulfill({ json: result })
  })
  await page.goto('/#/')
  await settings(page)
  await expect(button(page)).toBeDisabled()
  await key(page).fill('wrong')
  await button(page).click()
  await expect(page.getByRole('alert').filter({ hasText: 'Admin-Schlüssel ist ungültig.' }).filter({ visible: true })).toBeVisible()
  await expect(key(page)).toHaveValue('')
  await key(page).fill('test-admin-key')
  await button(page).click()
  await expect(page.getByText('Teilweise aktualisiert · UCL 2026/27', { exact: true }).filter({ visible: true })).toBeInViewport()
  await expect(page.getByRole('region', { name: 'Anbieterdaten aktualisieren', exact: true }).getByText('Nicht erfasst', { exact: true }).filter({ visible: true })).toBeVisible()
  await expect(page.getByText(/Abruf fehlgeschlagen; letzter gespeicherter Stand bleibt erhalten/).filter({ visible: true })).toBeVisible()
  await expect(key(page)).toHaveValue('')
  await page.screenshot({ path: testInfo.outputPath('manual-refresh.png') })
  expect(calls).toEqual(['Bearer wrong', 'Bearer test-admin-key'])
  expect(await page.evaluate(() => JSON.stringify([localStorage, sessionStorage]))).not.toContain('test-admin-key')
  await page.getByRole('navigation', { name: 'Hauptnavigation', exact: true }).filter({ visible: true }).getByRole('link', { name: 'Spiele', exact: true }).click()
  await expect(page.getByText('3:1', { exact: true }).first()).toBeVisible()
})

test('server cooldown survives local state and becomes retryable', async ({ page, api: _api }) => {
  await page.clock.install({ time: NOW })
  await page.route('**/api/internal/manual-refresh?*', route => route.fulfill({ status: 429, headers: { 'Retry-After': '50' }, json: { detail: 'Bitte warte kurz vor dem nächsten Abruf.' } }))
  await page.goto('/#/')
  await settings(page)
  await key(page).fill('test-admin-key')
  await button(page).click()
  await expect(page.getByRole('button', { name: 'Erneut in 50 s' }).filter({ visible: true })).toBeDisabled()
  await key(page).fill('test-admin-key')
  await page.clock.fastForward(51_000)
  await expect(button(page)).toBeEnabled()
})

test('a pending API refresh stays in the requested competition', async ({ page, api: _api }) => {
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  let requested = ''
  await page.route('**/api/internal/manual-refresh?*', async route => {
    requested = new URL(route.request().url()).searchParams.get('competition') ?? ''
    await gate
    await route.fulfill({ json: result })
  })
  await page.goto('/#/')
  await settings(page)
  await key(page).fill('test-admin-key')
  await button(page).click()
  await expect.poll(() => requested).toBe('ucl2026')
  await page.getByRole('banner').getByRole('button', { name: 'PL', exact: true }).click()
  release()
  await expect(page.getByText('Teilweise aktualisiert · UCL 2026/27', { exact: true }).filter({ visible: true })).toBeVisible()
  await expect(page.getByRole('banner').getByRole('button', { name: 'PL', exact: true })).toHaveAttribute('aria-pressed', 'true')
})


test('changing competition clears unsent admin credentials', async ({ page, api: _api }) => {
  await page.goto('/#/')
  await settings(page)
  await key(page).fill('unsent-admin-key')
  await expect(button(page)).toBeEnabled()
  const competition = page.getByRole('banner')
  await competition.getByRole('button', { name: 'WM', exact: true }).click()
  await expect(button(page)).toHaveCount(0)
  await competition.getByRole('button', { name: 'PL', exact: true }).click()
  await expect(key(page)).toHaveValue('')
  await expect(button(page)).toBeDisabled()
})


test('refresh cooldown remains active after leaving and reopening the data page', async ({ page, api: _api }) => {
  await page.clock.install({ time: NOW })
  await page.route('**/api/internal/manual-refresh?*', route => route.fulfill({ json: result }))
  await page.goto('/#/')
  await settings(page)
  await key(page).fill('test-admin-key')
  await button(page).click()
  await expect(page.getByRole('button', { name: 'Erneut in 60 s', exact: true })).toBeDisabled()
  await page.getByRole('navigation', { name: 'Hauptnavigation', exact: true }).filter({ visible: true }).getByRole('link', { name: 'Spiele', exact: true }).click()
  await settings(page)
  await key(page).fill('test-admin-key')
  await expect(page.getByRole('button', { name: 'Erneut in 60 s', exact: true })).toBeDisabled()
  await page.clock.fastForward(61_000)
  await expect(button(page)).toBeEnabled()
})

test('a refresh completed after navigation updates the reopened page cooldown', async ({ page, api: _api }) => {
  await page.clock.install({ time: NOW })
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/internal/manual-refresh?*', async route => { await gate; await route.fulfill({ json: result }) })
  await page.goto('/#/')
  await settings(page)
  await key(page).fill('test-admin-key')
  await button(page).click()
  await expect(page.getByRole('button', { name: 'API-Daten werden geladen…', exact: true })).toBeDisabled()
  await page.getByRole('navigation', { name: 'Hauptnavigation', exact: true }).filter({ visible: true }).getByRole('link', { name: 'Spiele', exact: true }).click()
  await settings(page)
  await expect(page.getByRole('button', { name: 'API-Daten werden geladen…', exact: true })).toBeDisabled()
  await expect(key(page)).toBeDisabled()
  release()
  await expect(page.getByRole('button', { name: 'Erneut in 60 s', exact: true })).toBeDisabled()
})
