import { chooseCompetition, expect, test } from './fixtures'

test('Premier League recommendations retain pending analysis status', async ({ page, api }) => {
  api.matches.epl2026[0].calculation_status = 'pending'
  await page.goto('/#/')
  await chooseCompetition(page, 'epl2026')
  await page.goto('/#/value-bets')

  const match = page.locator('article.match-card').filter({ hasText: 'Arsenal' }).first()
  await expect(match.getByRole('status')).toContainText('Analyse wird vorbereitet.')
  await match.locator('.fixture-probabilities > summary').click()
  await expect(match.getByText('Chancen werden angezeigt, sobald die Analyse abgeschlossen ist.')).toBeVisible()
})

test('World Cup analysis tabs fit without a horizontal tab scroller', async ({ page, api: _api }) => {
  await page.goto('/#/')
  await chooseCompetition(page, 'wc2026')
  await page.goto('/#/performance')

  const tabs = page.getByRole('tablist', { name: 'Auswertungsansicht' })
  await expect(tabs).toBeVisible()
  await expect.poll(() => tabs.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
  for (const label of ['Gespeicherte Tipps', 'Punkte & Verlauf', 'Modellvergleich', 'Bots & Rücktests']) {
    await expect(tabs.getByRole('tab', { name: label, exact: true })).toBeVisible()
  }
})

test('cumulative points chart states its unit and names each series', async ({ page, api: _api }) => {
  await page.goto('/#/performance')
  await page.getByRole('tab', { name: 'Punkte & Verlauf' }).click()

  const chart = page.getByRole('region', { name: 'Gespeicherter Punkteverlauf' })
  await expect(chart).toBeVisible()
  await expect(chart.getByText('Punkte', { exact: true })).toBeVisible()
  await expect(page.getByRole('group', { name: 'Kurven auswählen' }).getByRole('button', { name: 'Gemeinsame Tipps' })).toBeVisible()
  await expect(page.getByRole('group', { name: 'Kurven auswählen' }).getByRole('button', { name: 'Modell gesamt' })).toBeVisible()
})
