import { test, expect, fixture } from './fixtures'

test('competition is reachable in the header without opening a menu', async ({ page, api: _api }, testInfo) => {
  await page.goto('/#/')
  await expect(page.getByText('Bayern Munich', { exact: true }).first()).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('matchday.png'), fullPage: true })
  const header = page.getByRole('banner')
  await header.getByRole('combobox', { name: 'Wettbewerb', exact: true }).selectOption('epl2026')
  await expect(page.getByText('Chelsea', { exact: true }).first()).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

test('skip navigation focuses the content without replacing the route', async ({ page, api: _api }) => {
  await page.goto('/#/groups')
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'Zum Inhalt', exact: true })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/#\/groups$/)
  await expect(page.getByRole('main')).toBeFocused()
})

test('primary and analysis navigation keep every area reachable and mark the active section', async ({ page, api: _api }) => {
  await page.goto('/#/')
  const mobile = (page.viewportSize()?.width ?? 1440) < 1024
  const navigation = page.getByRole('navigation', { name: 'Hauptnavigation', exact: true }).filter({ visible: true })
  for (const [label, path] of [['Gemeinsame Tipps', 'performance'], ['Tabellen', 'groups'], ['Spiele', '']]) {
    const link = navigation.getByRole('link', { name: label, exact: true })
    await link.click()
    await expect(page).toHaveURL(new RegExp(`#/${path}$`))
    await expect(link).toHaveAttribute('aria-current', 'page')
    await expect(page.locator('main h1')).toBeVisible()
  }
  const trigger = navigation.getByRole('button', { name: mobile ? 'Mehr' : 'Analysen', exact: true })
  for (const [label, path] of [['Tipp-Chancen', 'value-bets'], ['Teams vergleichen', 'team-form'], ['Modell & Markt', 'edge'], ['Turnier simulieren', 'simulator']]) {
    await trigger.click()
    await page.getByRole('dialog').getByRole('link', { name: label }).click()
    await expect(page).toHaveURL(new RegExp(`#/${path}$`))
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(trigger).toHaveAttribute('data-active', 'true')
    await expect(page.locator('main h1')).toBeVisible()
    await trigger.click()
    await expect(page.getByRole('dialog').getByRole('link', { name: label })).toHaveAttribute('aria-current', 'page')
    await page.keyboard.press('Escape')
    await expect(trigger).toBeFocused()
  }
})

test('settings contain keyboard focus and restore it on dismissal', async ({ page, api: _api }) => {
  await page.goto('/#/')
  const mobile = (page.viewportSize()?.width ?? 1440) < 1024
  const trigger = page.getByRole('button', { name: mobile ? 'Mehr' : 'Einstellungen', exact: true })
  await trigger.click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect(dialog.getByRole('button', { name: 'Gespeicherte Daten neu laden', exact: true })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(dialog.getByRole('button', { name: 'Menü schliessen' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(trigger).toBeFocused()
})

test('saving a direct tip advances to the next game', async ({ page, api }) => {
  await page.goto('/#/')
  await page.getByRole('combobox', { name: 'Spiele filtern' }).selectOption('tips')
  await page.getByRole('spinbutton', { name: 'Tore Bayern Munich', exact: true }).fill('3')
  await page.getByRole('spinbutton', { name: 'Tore Arsenal', exact: true }).fill('0')
  await page.getByRole('button', { name: 'Speichern & nächstes Spiel', exact: true }).click()
  await expect(page.getByRole('spinbutton', { name: 'Tore Borussia Mönchengladbach', exact: true })).toBeFocused()
  expect(api.saves).toEqual([{ match_id: 'ucl-next', user_tip: '3:0', competition: 'ucl2026' }])
})

test('browser back restores search and the position in the fixture list', async ({ page, api }) => {
  for (let i = 0; i < 12; i++) api.matches.ucl2026.push(fixture(`extra-${i}`, 'Bayern Munich', `Opponent ${i}`))
  await page.goto('/#/')
  await page.getByRole('searchbox', { name: 'Team suchen' }).fill('Bayern')
  const link = page.getByRole('link', { name: 'Tipp ansehen: Bayern Munich gegen Opponent 11', exact: true })
  await link.scrollIntoViewIfNeeded()
  const scroll = await page.evaluate(() => window.scrollY)
  await link.click()
  await expect(page.locator('main h1')).toContainText('Opponent 11')
  await page.goBack()
  await expect(page.getByRole('searchbox', { name: 'Team suchen' })).toHaveValue('Bayern')
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeCloseTo(scroll, -1)
})

test('return to overview restores the fixture position after visiting analysis tabs', async ({ page, api }) => {
  for (let i = 0; i < 12; i++) api.matches.ucl2026.push(fixture(`return-${i}`, 'Bayern Munich', `Return opponent ${i}`))
  await page.goto('/#/')
  await page.getByRole('searchbox', { name: 'Team suchen' }).fill('Bayern')
  const link = page.getByRole('link', { name: 'Tipp ansehen: Bayern Munich gegen Return opponent 11', exact: true })
  await link.scrollIntoViewIfNeeded()
  const scroll = await page.evaluate(() => window.scrollY)
  await link.click()
  await page.getByRole('tab', { name: 'Form', exact: true }).click()
  await page.getByRole('tab', { name: 'Markt', exact: true }).click()
  await page.getByRole('button', { name: '← Zurück zur Übersicht', exact: true }).click()
  await expect(page).toHaveURL(/#\/$/)
  await expect(page.getByRole('searchbox', { name: 'Team suchen' })).toHaveValue('Bayern')
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeCloseTo(scroll, -1)
})
