import { test, expect, NOW } from './fixtures'

test('the recommendation and shared-tip action fit the first screen', async ({ page, api }) => {
  const match = api.matches.ucl2026[0]
  match.source_mode = 'odds+elo'
  match.input_provenance = {
    odds: { status: 'fresh', source: 'odds_api', observed_at: NOW.toISOString() },
    elo: { status: 'fresh', source: 'clubelo', observed_at: NOW.toISOString() },
  }
  await page.goto('/#/match/ucl-next')
  const save = page.getByRole('button', { name: 'Gemeinsamen Spieltipp speichern', exact: true })
  await expect(save).toBeEnabled()
  await expect(page.getByRole('heading', { name: 'Empfohlener Ergebnistipp' })).toBeVisible()
  const bounds = await save.boundingBox()
  expect(bounds).not.toBeNull()
  const mobile = (page.viewportSize()?.width ?? 1440) < 1024
  expect(bounds!.y + bounds!.height).toBeLessThan((page.viewportSize()?.height ?? 900) - (mobile ? 72 : 0))
  await expect(page.getByText('Für alle sichtbar', { exact: true })).toBeVisible()
})

test('source warnings stay visible while explanatory notes open on demand', async ({ page, api }) => {
  const match = api.matches.ucl2026[0]
  match.source_mode = 'odds+elo'
  match.input_provenance = {
    odds: { status: 'fresh', source: 'odds_api', observed_at: '2026-10-01T10:00:00Z' },
    elo: { status: 'fresh', source: 'clubelo', observed_at: NOW.toISOString() },
  }
  await page.goto('/#/match/ucl-next')
  const data = page.getByRole('region', { name: 'Datenlage', exact: true })
  await expect(data.getByText('Älterer Datenstand', { exact: true }).first()).toBeVisible()
  await expect(data.getByText('Nicht erfasst', { exact: true })).toBeVisible()
  const note = data.getByText(/Die Aktualität der gespeicherten Eingaben/)
  await expect(note).not.toBeVisible()
  await data.locator('summary').filter({ hasText: 'Was bedeutet die Datenlage?' }).click()
  await expect(note).toBeVisible()
  await expect(data.getByText(/Ihre Anzeige bestätigt nicht/)).toBeVisible()
  await page.locator('summary').filter({ hasText: 'Wie wird der Tipp gewählt?' }).click()
  await expect(page.getByText(/Erwartete Punkte sind der Durchschnitt/)).toBeVisible()
})
