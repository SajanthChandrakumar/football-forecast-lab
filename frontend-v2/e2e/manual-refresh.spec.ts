import { test, expect, NOW } from './fixtures'
import type { Page } from '@playwright/test'

async function settings(page: Page) {
  if ((page.viewportSize()?.width ?? 1440) < 1024) await page.getByRole('button', { name: 'Mehr', exact: true }).click()
  else await page.getByText('Einstellungen', { exact: true }).click()
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
  await expect(page.getByText('Nicht erfasst', { exact: true }).filter({ visible: true })).toBeVisible()
  await expect(page.getByText(/Abruf fehlgeschlagen; letzter gespeicherter Stand bleibt erhalten/).filter({ visible: true })).toBeVisible()
  await expect(key(page)).toHaveValue('')
  await page.screenshot({ path: testInfo.outputPath('manual-refresh.png') })
  expect(calls).toEqual(['Bearer wrong', 'Bearer test-admin-key'])
  expect(await page.evaluate(() => JSON.stringify([localStorage, sessionStorage]))).not.toContain('test-admin-key')
  if ((page.viewportSize()?.width ?? 1440) < 1024) await page.getByRole('button', { name: 'Menü schliessen' }).click()
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
  await page.getByLabel('Wettbewerb', { exact: true }).filter({ visible: true }).selectOption('epl2026')
  release()
  await expect(page.getByText('Teilweise aktualisiert · UCL 2026/27', { exact: true }).filter({ visible: true })).toBeVisible()
  await expect(page.getByLabel('Wettbewerb', { exact: true }).filter({ visible: true })).toHaveValue('epl2026')
})


test('changing competition clears unsent admin credentials', async ({ page, api: _api }) => {
  await page.goto('/#/')
  await settings(page)
  await key(page).fill('unsent-admin-key')
  await expect(button(page)).toBeEnabled()
  const competition = page.getByLabel('Wettbewerb', { exact: true }).filter({ visible: true })
  await competition.selectOption('wc2026')
  await expect(button(page)).toHaveCount(0)
  await competition.selectOption('epl2026')
  await expect(key(page)).toHaveValue('')
  await expect(button(page)).toBeDisabled()
})
