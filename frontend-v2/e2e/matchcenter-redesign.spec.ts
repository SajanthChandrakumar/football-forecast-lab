import { test, expect, NOW } from './fixtures'

test('games lead the first screen while radar and assistant remain available in their own views', async ({ page, api: _api }) => {
  await page.goto('/#/')
  const games = page.getByRole('tab', { name: 'Spiele', exact: true })
  await expect(games).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('region', { name: 'Spieltag-Assistent' })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Spieltag-Radar' })).toHaveCount(0)
  const card = page.locator('article.match-card').first()
  await expect(card).toContainText('Bayern Munich')
  const bounds = await card.boundingBox()
  expect(bounds!.y + 80).toBeLessThan((page.viewportSize()?.height ?? 900) - 80)
  await page.getByRole('tab', { name: 'Radar', exact: true }).click()
  await expect(page).toHaveURL(/view=radar/)
  await expect(page.getByRole('heading', { name: 'Spieltag-Radar' })).toBeVisible()
  await page.getByRole('tab', { name: 'Tipp-Assistent', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Spieltag-Assistent' })).toBeVisible()
  await page.getByLabel('Tipp für Bayern Munich gegen Arsenal', { exact: true }).fill('3:0')
  await page.getByRole('tab', { name: 'Spiele', exact: true }).click()
  await page.getByRole('tab', { name: 'Tipp-Assistent', exact: true }).click()
  await expect(page.getByLabel('Tipp für Bayern Munich gegen Arsenal', { exact: true })).toHaveValue('3:0')
})

test('tab keyboard controls and browser history restore the selected view', async ({ page, api: _api }) => {
  await page.goto('/#/?view=radar')
  const radar = page.getByRole('tab', { name: 'Radar', exact: true })
  await expect(radar).toHaveAttribute('aria-selected', 'true')
  await radar.focus()
  await page.keyboard.press('End')
  await expect(page.getByRole('tab', { name: 'Tipp-Assistent', exact: true })).toBeFocused()
  await expect(page).toHaveURL(/view=assistant/)
  await page.goBack()
  await expect(radar).toHaveAttribute('aria-selected', 'true')
})

test('match analysis keeps a tip draft while moving through its data tabs', async ({ page, api: _api }) => {
  await page.goto('/#/match/ucl-next')
  const field = page.getByRole('spinbutton', { name: 'Tore Bayern Munich', exact: true })
  await field.fill('4')
  for (const name of ['Form', 'Aufstellungen', 'Markt', 'Modelldaten', 'Überblick']) {
    await page.getByRole('tab', { name, exact: true }).click()
    await expect(page.getByRole('tab', { name, exact: true })).toHaveAttribute('aria-selected', 'true')
  }
  await expect(field).toHaveValue('4')
})

test('cards keep unavailable chances honest and label zero probabilities', async ({ page, api }) => {
  delete api.matches.ucl2026[0].odds
  delete api.matches.ucl2026[0].probabilities
  api.matches.ucl2026[1].odds = undefined
  api.matches.ucl2026[1].source_mode = 'elo-only'
  api.matches.ucl2026[1].probabilities = { home: 1, draw: 0, away: 0 }
  await page.goto('/#/')
  await expect(page.locator('article.match-card').first()).toContainText(/Chancen.*nicht verfügbar/i)
  await page.locator('summary').filter({ hasText: 'Spielwoche 2' }).click()
  const card = page.locator('article.match-card').filter({ hasText: 'Borussia Mönchengladbach' })
  await expect(card.getByText('0%', { exact: true })).toHaveCount(2)
  await expect(card).toContainText('Elo')
})

test('form keeps the last ten archived games and league scope separate from lineup requests', async ({ page, api }) => {
  api.matches.ucl2026[0].home_form = {
    status: 'fresh', on_fire: false, form: ['W'], source: 'espn+fotmob', scope: 'league',
    matches: Array.from({ length: 12 }, (_, index) => ({
      fixture_id: `history-${index}`, opponent_name: `History opponent ${index}`,
      score: '2:1', result: 'W' as const, competition_name: 'Premier League', venue: 'home' as const,
      played_at: new Date(NOW.getTime() - (index + 1) * 86_400_000).toISOString(),
    })),
  }
  await page.goto('/#/match/ucl-next?view=form')
  const form = page.getByRole('tabpanel', { name: 'Form', exact: true })
  await expect(form).toContainText('ESPN + FotMob')
  await expect(form).toContainText('nur zuletzt erfasste Premier-League-Spiele, keine anderen Wettbewerbe')
  for (let index = 0; index < 10; index++) await expect(form.getByText(`History opponent ${index}`, { exact: false })).toBeVisible()
  await expect(form.getByText('History opponent 10', { exact: false })).toHaveCount(0)
  await expect(form.getByRole('button', { name: 'Aufstellung ansehen', exact: true })).toHaveCount(0)
  await page.getByRole('tab', { name: 'Aufstellungen', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Aufstellung ansehen', exact: true })).toHaveCount(10)
})
