import { test, expect, NOW, chooseCompetition } from './fixtures'

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

test('club form shows the five newest verified all-competition games and expands to ten', async ({ page, api }) => {
  api.matches.ucl2026[0].home_form = {
    status: 'fresh', on_fire: false, form: ['W'], source: 'espn+fotmob', scope: 'all_competitions',
    coverage: { available: 10, required: 10, complete: true }, validation_version: 'senior-men-v1',
    matches: Array.from({ length: 12 }, (_, index) => ({
      fixture_id: `history-${index}`, opponent_name: `History opponent ${index}`,
      home_id: 'bayern-id', home_team: 'Bayern Munich', home_logo: null, away_id: `opponent-${index}`, away_team: `History opponent ${index}`, away_logo: null,
      identity_verified: index !== 6, competition_kind: index === 0 ? 'cup' as const : 'league' as const,
      score: '2:1', goals_for: 2, goals_against: 1, result: 'W' as const, competition_name: index === 0 ? 'DFB-Pokal' : 'Bundesliga', venue: 'home' as const,
      played_at: new Date(NOW.getTime() - (index + 1) * 86_400_000).toISOString(),
    })),
  }
  await page.goto('/#/match/ucl-next?view=form')
  const form = page.getByRole('tabpanel', { name: 'Form', exact: true })
  await expect(form).toContainText('ESPN + FotMob')
  const newest = form.locator('li').filter({ hasText: 'History opponent 0' }).first()
  await expect(newest).toContainText('Bayern Munich')
  await expect(newest).toContainText('2:1')
  await expect(newest).toContainText('History opponent 0')
  await expect(newest.getByRole('img', { name: 'Bayern Munich: Wappen nicht verfügbar' })).toBeVisible()
  await expect(newest.getByRole('img', { name: 'History opponent 0: Wappen nicht verfügbar' })).toBeVisible()
  await expect(newest.getByRole('group', { name: 'Bayern Munich, ausgewählte Mannschaft' })).toBeVisible()
  for (let index = 0; index < 5; index++) await expect(form.getByText(`History opponent ${index}`, { exact: true })).toBeVisible()
  await expect(form.getByText('History opponent 5', { exact: true })).toHaveCount(0)
  await expect(form.getByText('History opponent 6', { exact: true })).toHaveCount(0)
  await expect(form.getByRole('button', { name: 'Weitere Spiele (10)', exact: true })).toBeVisible()
  await form.getByRole('button', { name: 'Weitere Spiele (10)', exact: true }).click()
  for (let index = 0; index < 10; index++) if (index !== 6) await expect(form.getByText(`History opponent ${index}`, { exact: true })).toBeVisible()
  await form.getByRole('button', { name: 'Pokal', exact: true }).click()
  await expect(form.getByText('Spiele', { exact: true }).locator('..')).toContainText('1')
  await expect(form.getByText('History opponent 0', { exact: true })).toBeVisible()
  await form.getByRole('button', { name: 'Alle Pflichtspiele', exact: true }).click()
  await expect(form.getByRole('button', { name: 'Aufstellung ansehen', exact: true })).toHaveCount(0)
  await page.getByRole('tab', { name: 'Aufstellungen', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Aufstellung ansehen', exact: true })).toHaveCount(10)
})

test('team comparison uses the same verified club form rows as match details', async ({ page, api }) => {
  api.matches.ucl2026[0].home_form = {
    status: 'fresh', on_fire: false, form: ['W'], source: 'espn', scope: 'all_competitions',
    coverage: { available: 1, required: 10, complete: false }, validation_version: 'senior-men-v1',
    matches: [{
      fixture_id: 'comparison-history', played_at: new Date(NOW.getTime() - 86_400_000).toISOString(),
      opponent_id: 'arsenal-id', opponent_name: 'Arsenal', venue: 'home', score: '2:0',
      goals_for: 2, goals_against: 0, result: 'W', provider: 'espn',
      home_id: 'bayern-id', home_team: 'Bayern Munich', home_logo: null,
      away_id: 'arsenal-id', away_team: 'Arsenal', away_logo: null,
      competition_id: 'bundesliga', competition_name: 'Bundesliga', competition_kind: 'league',
      result_type: 'FT', identity_verified: true,
    }],
  }
  await page.goto('/#/')
  await chooseCompetition(page, 'ucl2026')
  await page.goto('/#/team-form')
  const history = page.getByRole('region', { name: 'Bayern Munich Pflichtspielform' })
  await expect(history).toBeVisible()
  await expect(history).toContainText('Arsenal')
  await expect(history).toContainText('2:0')
})

test('pending club calculations stay unavailable until prediction and cache refresh complete', async ({ page, api }, testInfo) => {
  test.skip(testInfo.project.name !== 'phone-375', 'One phone flow covers the pending calculation state.')
  const match = api.matches.ucl2026[0]
  Object.assign(match, {
    calculation_status: 'pending',
    top_tip: 'N/A',
    model_tip: null,
    probabilities: null,
    source_mode: 'unavailable',
    status: 'unavailable',
    odds: { home: 1.05, draw: 20, away: 50 },
    bots: { broker: { tip: '0:9' } },
  })
  api.prediction = {
    model_tip: '3:1', top_tip: '3:1',
    probabilities: { home: .62, draw: .25, away: .13 },
    source_mode: 'elo-only', status: 'fresh', observed_at: NOW.toISOString(),
    input_provenance: { elo: { status: 'fresh', source: 'clubelo', observed_at: NOW.toISOString() } },
  }
  let releasePrediction!: () => void
  api.predictionGate = new Promise<void>((resolve) => { releasePrediction = resolve })

  await page.goto('/#/')
  const row = page.locator('article.match-card').filter({ hasText: match.home_team }).first()
  await expect(row.getByText('Analyse wird vorbereitet.', { exact: true })).toBeVisible()
  await expect(row.locator('.match-card-pick-value')).toHaveText('–')
  await expect(row).not.toContainText('92%')

  await row.getByRole('link', { name: /Tipp ansehen/ }).click()
  const recommendation = page.getByRole('region', { name: 'Empfohlener Ergebnistipp' })
  await expect(recommendation.getByText('Analyse wird vorbereitet.', { exact: true })).toBeVisible()
  await expect.poll(() => api.predictionRequests.map(({ matchId }) => matchId)).toEqual(['ucl-next'])
  await page.getByRole('tab', { name: 'Modelldaten', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Bot-Vorschläge', exact: true })).toHaveCount(0)
  const hints = page.locator('section.match-card').filter({ has: page.getByRole('heading', { name: 'Spielhinweise', exact: true }) })
  await expect(hints.getByText('Analyse wird vorbereitet.', { exact: true })).toBeVisible()
  await expect(hints.getByText('Hoch', { exact: true })).toHaveCount(0)

  releasePrediction()
  await expect.poll(() => api.predictionResponses).toBe(1)
  await expect(page.getByRole('heading', { name: 'Bot-Vorschläge', exact: true })).toHaveCount(0)
  await expect(hints).toContainText('Hoch')
  await page.getByRole('tab', { name: 'Überblick', exact: true }).click()
  await expect(recommendation.locator('.display-num')).toHaveText('3:1')

  await page.goto('/#/')
  await expect(row.getByText('Analyse wird vorbereitet.', { exact: true })).toBeVisible()
  Object.assign(match, {
    calculation_status: undefined,
    top_tip: '3:1', model_tip: '3:1',
    probabilities: { home: .62, draw: .25, away: .13 },
    source_mode: 'elo-only', status: 'fresh', observed_at: NOW.toISOString(),
  })
  if ((page.viewportSize()?.width ?? 1440) < 1024) await page.getByRole('button', { name: 'Mehr', exact: true }).click()
  else await page.getByRole('button', { name: 'Einstellungen', exact: true }).click()
  await page.getByRole('button', { name: 'Gespeicherte Daten neu laden', exact: true }).click()
  await expect(page.getByText(/Gespeicherte Daten für UCL/)).toBeVisible()
  const closeMenu = page.getByRole('button', { name: 'Menü schliessen', exact: true })
  if (await closeMenu.count()) await closeMenu.click()
  await expect(row.getByText('Analyse wird vorbereitet.', { exact: true })).toHaveCount(0)
  await expect(row.locator('.match-card-pick-value')).toHaveText('3:1')
})
