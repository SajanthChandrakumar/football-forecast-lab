import { test, expect, NOW, chooseCompetition } from './fixtures'
import { dataStatusFixture } from './data-status-fixture'
import type { CompetitionId } from '../src/lib/types'

test('API overview is reachable and distinguishes shared allowance from observed data', async ({ page, api: _api }) => {
  const requests: string[] = []
  await page.route('**/api/data-status?*', route => { requests.push(route.request().method()); return route.fulfill({ json: dataStatusFixture('ucl2026', NOW.toISOString()) }) })
  await page.goto('/#/')
  await page.getByRole('button', { name: (page.viewportSize()?.width ?? 1440) < 1024 ? 'Mehr' : 'Analysen', exact: true }).click()
  await page.getByRole('dialog').getByRole('navigation', { name: 'Analysen', exact: true }).getByRole('link', { name: /^API & Daten/ }).click({ timeout: 5000 })
  await expect(page).toHaveURL(/#\/data-sources$/)
  await expect(page.getByRole('heading', { name: 'API & Daten', exact: true })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Datenquellen', exact: true }).getByRole('article', { name: 'Spiele & Resultate', exact: true })).toContainText('ESPN')
  await expect(page.getByRole('article', { name: 'Teamform', exact: true })).toContainText('Abdeckung: 5 von 10 Mannschaften')
  const odds = page.getByRole('article', { name: 'The Odds API', exact: true })
  await expect(odds.getByText('0 Credits', { exact: true })).toBeVisible()
  await expect(odds).toContainText('380 Credits')
  await expect(page.getByText('Gemeinsam für WM, UCL und PL', { exact: true })).toBeVisible()
  await expect(page.getByText(/Für ESPN und ClubElo ist kein Restkontingent erfasst/)).toBeVisible()
  expect(requests).toEqual(['GET'])
})

test('API overview follows competition and keeps global quotas separate', async ({ page, api: _api }) => {
  const requests: string[] = []
  await page.route('**/api/data-status?*', route => { const comp = new URL(route.request().url()).searchParams.get('competition') as CompetitionId; requests.push(comp); return route.fulfill({ json: dataStatusFixture(comp, NOW.toISOString()) }) })
  await page.goto('/#/data-sources')
  await expect(page.getByRole('region', { name: 'Datenquellen', exact: true })).toBeVisible()
  await chooseCompetition(page, 'epl2026')
  await expect(page.getByText('Datenquellen für PL 2026/27', { exact: true })).toBeVisible()
  await expect(page.getByLabel('Admin-Schlüssel', { exact: true })).toBeVisible()
  await chooseCompetition(page, 'wc2026')
  await expect(page.getByText('Datenquellen für WM 2026', { exact: true })).toBeVisible()
  await expect(page.getByLabel('Admin-Schlüssel', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('article', { name: 'The Odds API', exact: true })).toContainText('380 Credits')
  expect(requests).toEqual(['ucl2026', 'epl2026', 'wc2026'])
})

test('unknown quotas stay unknown and cannot become zero or unlimited', async ({ page, api: _api }) => {
  await page.route('**/api/data-status?*', route => route.fulfill({ json: dataStatusFixture('ucl2026', NOW.toISOString(), true) }))
  await page.goto('/#/data-sources')
  for (const provider of ['The Odds API', 'API-Football']) {
    const card = page.getByRole('article', { name: provider, exact: true })
    await expect(card).toContainText('Restkontingent nicht bekannt')
    await expect(card).toContainText('App-Verbrauch nicht bekannt')
    await expect(card.getByText('0 Credits', { exact: true })).toHaveCount(0)
    await expect(card).not.toContainText('unbegrenzt')
  }
})

test('a failed status reload preserves the last known overview and can retry', async ({ page, api: _api }) => {
  let failed = false
  await page.route('**/api/data-status?*', route => failed ? route.fulfill({ status: 503, json: { detail: 'Unavailable' } }) : route.fulfill({ json: dataStatusFixture('ucl2026', NOW.toISOString()) }))
  await page.goto('/#/data-sources')
  await expect(page.getByRole('article', { name: 'The Odds API', exact: true })).toBeVisible()
  failed = true
  await page.getByRole('button', { name: 'Übersicht neu laden', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: /Datenübersicht konnte nicht aktualisiert werden/ })).toBeVisible()
  await expect(page.getByRole('article', { name: 'The Odds API', exact: true })).toContainText('380 Credits')
  failed = false
  await page.getByRole('button', { name: 'Übersicht neu laden', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: /Datenübersicht konnte nicht aktualisiert werden/ })).toHaveCount(0)
})

test('API overview stays readable in the reported 788 pixel tablet viewport', async ({ page, api: _api }, testInfo) => {
  await page.setViewportSize({ width: 788, height: 827 })
  await page.route('**/api/data-status?*', route => route.fulfill({ json: dataStatusFixture('ucl2026', NOW.toISOString()) }))
  await page.goto('/#/data-sources')
  await expect(page.getByRole('heading', { name: 'API & Daten', exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('api-data-tablet-788.png'), fullPage: true })
})


test('future capture timestamps are never described as just captured', async ({ page, api: _api }) => {
  const data = dataStatusFixture('ucl2026', NOW.toISOString())
  const future = new Date(NOW.getTime() + 86400000).toISOString()
  data.quotas.providers.odds.reported.status = 'unknown'
  data.quotas.providers.odds.reported.observed_at = future
  data.datasets[0].status = 'stale'
  data.datasets[0].observed_at = future
  await page.route('**/api/data-status?*', route => route.fulfill({ json: data }))
  await page.goto('/#/data-sources')
  const odds = page.getByRole('article', { name: 'The Odds API', exact: true })
  await expect(odds).toBeVisible()
  await expect(odds).toContainText('Restkontingent nicht bekannt')
  await expect(odds).not.toContainText('gerade eben')
  await expect(page.getByRole('article', { name: 'Spiele & Resultate', exact: true })).not.toContainText('gerade eben')
})
