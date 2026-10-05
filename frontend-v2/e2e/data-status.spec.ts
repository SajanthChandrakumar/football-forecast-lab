import { test, expect, NOW } from './fixtures'

test('overview and detail explain source age and missing lineup evidence', async ({ page, api }) => {
  const match = api.matches.ucl2026[0]
  match.source_mode = 'odds+elo'
  match.input_provenance = {
    odds: { status: 'fresh', source: 'odds_api', observed_at: '2026-10-01T10:00:00Z' },
    elo: { status: 'fresh', source: 'clubelo', observed_at: NOW.toISOString() },
  }
  await page.goto('/#/')
  const row = page.locator('article.fixture-row').filter({ hasText: match.home_team }).first()
  const summary = row.locator('summary').filter({ hasText: /^Datenlage:/ })
  await expect(summary).toContainText('Älterer Datenstand')
  await summary.click()
  await expect(row.getByText('Nicht erfasst', { exact: true })).toBeVisible()
  await row.getByRole('link', { name: /Tipp ansehen/ }).click()
  const data = page.getByRole('region', { name: 'Datenlage', exact: true })
  await expect(data).toBeVisible()
  await expect(data).toContainText('The Odds API')
  await expect(data).toContainText('ClubElo')
  await expect(data).toContainText('Älterer Datenstand')
  await expect(data).toContainText('vor 2 Tagen')
  await expect(data).toContainText('Nicht erfasst')
  await expect(data).not.toContainText('noch nicht veröffentlicht')
  await expect(page.getByRole('heading', { name: 'Empfohlener Ergebnistipp' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Gemeinsamen Spieltipp speichern', exact: true })).toBeEnabled()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)
  expect(overflow).toBe(false)
})

test('Elo-only data and unknown timestamps stay explicit beside the suggestion', async ({ page, api }) => {
  const match = api.matches.ucl2026[0]
  match.odds = undefined
  match.source_mode = 'elo-only'
  match.input_provenance = { elo: { status: 'fresh', source: 'clubelo' } }
  await page.goto('/#/match/ucl-next')
  const data = page.getByRole('region', { name: 'Datenlage', exact: true })
  await expect(data).toContainText('nur Elo')
  await expect(data).toContainText('Buchmacherquoten fehlen')
  await expect(data).toContainText('Aktualität nicht bestätigt')
  await expect(data).toContainText('Zeitpunkt nicht verfügbar')
  await expect(data).not.toContainText('Datenstand belegt')
})


test('data evidence follows the displayed prediction when the match cache differs', async ({ page, api }) => {
  const match = api.matches.ucl2026[0]
  match.source_mode = 'odds+elo'
  match.input_provenance = {
    odds: { source: 'odds_api', status: 'fresh', observed_at: NOW.toISOString() },
    elo: { source: 'clubelo', status: 'fresh', observed_at: NOW.toISOString() },
  }
  api.prediction = {
    model_tip: '3:0', source_mode: 'elo-only', observed_at: NOW.toISOString(),
    input_provenance: { elo: { source: 'elo', status: 'fresh' } },
  }
  await page.goto('/#/match/ucl-next')
  const recommendation = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Empfohlener Ergebnistipp', exact: true }) })
  await expect(recommendation.getByText('3:0', { exact: true })).toBeVisible()
  const data = page.getByRole('region', { name: 'Datenlage', exact: true })
  await expect(data).toContainText('nur Elo')
  await expect(data).toContainText('Elo-Daten')
  await expect(data).toContainText('Zeitpunkt nicht verfügbar')
  await expect(data).not.toContainText('Datenstand belegt')
  await expect(data).not.toContainText('ClubElo')
})
