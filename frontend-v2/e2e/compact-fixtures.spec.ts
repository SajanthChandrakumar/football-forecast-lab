import { enterEditorKey, expect, fixture, test } from './fixtures'

test('compact fixture outcomes stay disclosed while order, model tip and data status remain visible', async ({ page, api }) => {
  await page.goto('/#/')
  const match = api.matches.ucl2026[0]
  const row = page.locator('article.match-card').filter({ hasText: match.home_team }).first()
  await expect(row).toContainText(match.home_team)
  await expect(row).toContainText(match.away_team)
  await expect(row.locator('.match-card-team-home')).toContainText(match.home_team)
  await expect(row.locator('.match-card-team-away')).toContainText(match.away_team)
  const teamOrder = await row.locator('.match-card-scoreboard .match-card-team').evaluateAll((teams) =>
    teams.map((team) => team.classList.contains('match-card-team-home') ? 'home' : 'away'),
  )
  expect(teamOrder).toEqual(['home', 'away'])
  await expect(row.locator('.match-card-pick-label')).toHaveText('Modelltipp')
  await expect(row.locator('.match-card-pick-value')).toHaveText('2:1')
  await expect(row.getByText(/^Datenlage:/)).toBeVisible()
  await expect(row.getByRole('img', { name: /Spielausgangschancen/ })).not.toBeVisible()

  const disclosure = row.locator('.fixture-probabilities > summary')
  await expect(disclosure).toBeVisible()
  await disclosure.focus()
  await page.keyboard.press('Enter')
  await expect(row.getByRole('img', { name: /Spielausgangschancen/ })).toBeVisible()
})

test('fresh, pending, played and missing-data fixtures keep their result and source status clear', async ({ page, api }) => {
  const fresh = api.matches.ucl2026[0]
  const pending = fixture('ucl-pending', 'Pending Home', 'Pending Away', -60 * 60_000)
  const played = fixture('ucl-played', 'Played Home', 'Played Away', -2 * 86_400_000)
  Object.assign(played, { actual_score: '1:0', completed: true })
  const missing = fixture('ucl-missing', 'Missing Home', 'Missing Away', 26 * 60 * 60_000)
  Object.assign(missing, { odds: undefined, probabilities: null, top_tip: 'N/A', status: 'unavailable', source_mode: 'unavailable' })
  api.matches.ucl2026 = [fresh, pending, played, missing]

  await page.goto('/#/')
  const freshRow = page.locator('article.match-card').filter({ hasText: fresh.home_team }).first()
  await expect(freshRow.locator('.match-card-pick-label')).toHaveText('Modelltipp')
  await expect(freshRow.getByText(/^Datenlage:/)).toBeVisible()

  await page.getByRole('combobox', { name: 'Spiele filtern' }).selectOption('upcoming')
  const missingRow = page.locator('article.match-card').filter({ hasText: 'Missing Home' }).first()
  await expect(missingRow.getByText(/Datenlage: Eingaben nicht belegt/)).toBeVisible()
  await missingRow.locator('.fixture-probabilities > summary').click()
  await expect(missingRow.getByText('Spielausgangschancen nicht verfügbar.', { exact: true })).toBeVisible()

  await page.getByRole('combobox', { name: 'Spiele filtern' }).selectOption('pending')
  const pendingRow = page.locator('article.match-card').filter({ hasText: 'Pending Home' }).first()
  await expect(pendingRow.getByText('Ergebnis ausstehend', { exact: true })).toBeVisible()
  await expect(pendingRow.locator('.match-card-pick-label')).toHaveText('Ergebnis')
  await expect(pendingRow.locator('.match-card-pick-value')).toHaveText('–')
  await expect(pendingRow.getByText(/^Datenlage:/)).toBeVisible()
  if ((page.viewportSize()?.width ?? 1440) <= 680) {
    const tools = await pendingRow.locator('.fixture-row-tools').boundingBox()
    const disclosure = await pendingRow.locator('.fixture-probabilities').boundingBox()
    expect(Math.abs(disclosure!.width - tools!.width)).toBeLessThan(1)
  }

  await page.getByRole('combobox', { name: 'Spiele filtern' }).selectOption('played')
  const playedRow = page.locator('article.match-card').filter({ hasText: 'Played Home' }).first()
  await expect(playedRow.locator('.match-card-pick-label')).toHaveText('Ergebnis')
  await expect(playedRow.locator('.match-card-pick-value')).toHaveText('1:0')
  await expect(playedRow.getByText('Modelltipp: 2:1', { exact: true })).toBeVisible()
  if ((page.viewportSize()?.width ?? 1440) <= 680) {
    const tools = await playedRow.locator('.fixture-row-tools').boundingBox()
    const action = await playedRow.locator('.match-card-action').boundingBox()
    expect(Math.abs(action!.width - tools!.width)).toBeLessThan(1)
  }
})

test('shared-tip rows stay open and save-and-next focuses the next fixture', async ({ page, api }) => {
  await page.goto('/#/')
  await page.getByRole('combobox', { name: 'Spiele filtern' }).selectOption('tips')

  const first = page.locator('article.match-card').filter({ hasText: 'Bayern Munich' }).first()
  const next = page.locator('article.match-card').filter({ hasText: 'Borussia Mönchengladbach' }).first()
  const nextHomeInput = next.getByRole('spinbutton', { name: 'Tore Borussia Mönchengladbach', exact: true })
  await expect(first.locator('.match-card-editor')).toBeVisible()
  await expect(first.getByRole('spinbutton', { name: 'Tore Bayern Munich', exact: true })).toBeEditable()
  await first.getByRole('spinbutton', { name: 'Tore Bayern Munich', exact: true }).fill('1')
  await first.getByRole('spinbutton', { name: 'Tore Arsenal', exact: true }).fill('0')
  await first.getByRole('button', { name: 'Speichern & nächstes Spiel', exact: true }).click()
  await enterEditorKey(page, api.validEditorKey)
  await expect(page.getByRole('status').filter({ hasText: 'Gemeinsamer Tipp 1:0 für Bayern Munich gegen Arsenal gespeichert.' })).toBeVisible()
  await expect(nextHomeInput).toBeFocused()
  expect(api.saves.map(({ user_tip }) => user_tip)).toContain('1:0')
})

test('pending club analysis stays explained while chances are closed', async ({ page, api }) => {
  Object.assign(api.matches.ucl2026[0], {
    calculation_status: 'pending', top_tip: 'N/A', probabilities: null,
    status: 'unavailable', source_mode: 'unavailable',
  })
  await page.goto('/#/')
  const row = page.locator('article.fixture-row').filter({ hasText: 'Bayern Munich' }).first()
  await expect(row.getByText(/^Datenlage:/)).toBeVisible()
  await expect(row.getByText('Analyse wird vorbereitet.', { exact: true })).toBeVisible()
  await expect(row.locator('.fixture-probabilities')).toHaveJSProperty('open', false)
  await expect(row.getByRole('img', { name: /Spielausgangschancen/ })).not.toBeVisible()
})

test('compact row controls retain 44px hit areas', async ({ page, api }) => {
  await page.goto('/#/')
  const match = api.matches.ucl2026[0]
  const row = page.locator('article.fixture-row').filter({ hasText: match.home_team }).first()
  const dataSummary = row.locator('.fixture-data > summary')
  const chanceSummary = row.locator('.fixture-probabilities > summary')
  const action = row.locator('.match-card-action')
  await expect(dataSummary).toBeVisible()
  await expect(chanceSummary).toBeVisible()
  await expect(action).toBeVisible()
  const heights = await row.locator('.fixture-data > summary, .fixture-probabilities > summary, .match-card-action').evaluateAll(
    (controls) => controls.map((control) => control.getBoundingClientRect().height),
  )
  expect(heights).toHaveLength(3)
  expect(heights.every((height) => height >= 44)).toBe(true)
})

test('value-bet fixture rows span the grid and leave room for long team names', async ({ page, api }) => {
  const names = [
    ['Borussia Mönchengladbach am Niederrhein', 'Club Atlético de Madrid International'],
    ['Arsenal Football Club of North London', 'Paris Saint-Germain Saint-Germain-en-Laye'],
  ]
  api.matches.ucl2026.forEach((match, index) => {
    const [home, away] = names[index]
    Object.assign(match, { home_team: home, away_team: away, home_disp: home, away_disp: away })
    if (match.raw_match) Object.assign(match.raw_match, { home_team: home, away_team: away })
  })

  await page.goto('/#/value-bets')
  await page.getByRole('button', { name: 'Alle kommenden Spiele', exact: true }).click()
  const grid = page.locator('.match-grid').filter({ has: page.locator('article.fixture-row') }).first()
  const rows = grid.locator('article.fixture-row')
  await expect(rows).toHaveCount(2)
  const geometry = await grid.evaluate((element) => {
    const style = getComputedStyle(element)
    const contentWidth = element.getBoundingClientRect().width - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)
    return [...element.querySelectorAll<HTMLElement>(':scope > .fixture-row')].map((row) => ({
      width: row.getBoundingClientRect().width,
      nameWidths: [...row.querySelectorAll<HTMLElement>('.match-card-team-name')].map((name) => name.getBoundingClientRect().width),
      contentWidth,
    }))
  })
  for (const row of geometry) {
    expect(row.width).toBeGreaterThan(row.contentWidth * 0.95)
    expect(Math.min(...row.nameWidths)).toBeGreaterThan(100)
  }
})
