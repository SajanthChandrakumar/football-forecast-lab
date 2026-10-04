import { test, expect, chooseCompetition } from './fixtures'

const routes = ['', 'match/ucl-long', 'team-form', 'groups', 'value-bets', 'edge', 'performance', 'simulator']

for (const theme of ['dark', 'light']) test(`each view fits the viewport in ${theme} mode`, async ({ page, api: _api }, testInfo) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.addInitScript(value => localStorage.setItem('theme', value), theme)
    for (const route of routes) {
      await page.goto(`/#/${route}`)
      await expect(page.locator('main h1')).toBeVisible()
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
      if (route === 'team-form') {
        await expect(page.getByText('2 von 4 ausgewählt')).toBeVisible()
        await page.getByRole('button', { name: 'Borussia Mönchengladbach', exact: true }).click()
        await page.getByRole('button', { name: 'Club Atlético de Madrid', exact: true }).click()
      }
      if (route === 'match/ucl-long') {
        await expect(page.getByRole('button', { name: 'Gemeinsamen Spieltipp speichern', exact: true })).toBeVisible()
        await page.locator('summary').filter({ hasText: 'Weitere Daten zur Analyse' }).click()
      }
      if (route === 'performance') {
        await expect(page.getByText('2 Spiele in der gemeinsamen Stichprobe')).toBeVisible()
        await page.locator('summary').filter({ hasText: 'Weitere Auswertungen und Rücktests' }).click()
      }
      if (route === '') await expect(page.getByText('Bayern Munich', { exact: true }).first()).toBeVisible()
      const overflow = await page.evaluate(() => {
        const width = document.documentElement.clientWidth
        return [...document.querySelectorAll<HTMLElement>('body *')].filter(element => {
          const box = element.getBoundingClientRect()
          return box.width > 0 && box.right > width + 1 && getComputedStyle(element).position !== 'absolute' && !element.closest('.overflow-x-auto')
        }).map(element => ({ tag: element.tagName, className: element.className, text: element.textContent?.slice(0, 90), right: Math.round(element.getBoundingClientRect().right) })).slice(0, 12)
      })
      expect(overflow, `${theme} /${route} must fit`).toEqual([])
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), `${route} page scroll width`).toBe(true)
    }
  expect(errors).toEqual([])
  await page.goto('/#/team-form')
  await expect(page.getByText('4 von 4 ausgewählt')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('team-comparison.png'), fullPage: true })
})

test('mobile menu contains focus, closes with Escape and returns focus', async ({ page, api: _api }) => {
  test.skip((page.viewportSize()?.width ?? 1440) >= 1024, 'Desktop uses the sidebar')
  await page.goto('/#/')
  const more = page.getByRole('button', { name: 'Mehr', exact: true })
  await more.click()
  const dialog = page.getByRole('dialog', { name: 'Analysen und Einstellungen' })
  await expect(dialog).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect(dialog.getByRole('button', { name: 'Gespeicherte Daten neu laden', exact: true })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(dialog.getByRole('button', { name: 'Menü schliessen' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(more).toBeFocused()
  await chooseCompetition(page, 'epl2026')
  await expect(page.getByText('Chelsea', { exact: true }).first()).toBeVisible()
})


test('phone forms keep readable text and touch-sized comparison controls', async ({ page, api: _api }) => {
  test.skip((page.viewportSize()?.width ?? 1440) > 390, 'Phone input and touch sizing')
  await page.goto('/#/team-form')
  await expect(page.getByText('2 von 4 ausgewählt')).toBeVisible()
  expect(await page.getByRole('textbox', { name: 'Teams suchen und hinzufügen' }).evaluate(element => parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(16)
  const add = page.getByRole('button', { name: 'Paris Saint-Germain', exact: true })
  expect((await add.boundingBox())?.height).toBeGreaterThanOrEqual(44)
  const remove = page.getByRole('button', { name: 'Arsenal aus dem Vergleich entfernen', exact: true })
  expect((await remove.boundingBox())?.height).toBeGreaterThanOrEqual(44)
})


test('blocked browser storage does not prevent navigation or theme changes', async ({ page, api: _api }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.addInitScript(() => {
    Storage.prototype.getItem = () => { throw new DOMException('Storage blocked', 'SecurityError') }
    Storage.prototype.setItem = () => { throw new DOMException('Storage blocked', 'QuotaExceededError') }
  })
  await page.goto('/#/')
  await expect(page.getByText('Bayern Munich', { exact: true }).first()).toBeVisible()
  await chooseCompetition(page, 'epl2026')
  await expect(page.getByText('Chelsea', { exact: true }).first()).toBeVisible()
  if ((page.viewportSize()?.width ?? 1440) < 1024) await page.getByRole('button', { name: 'Mehr', exact: true }).click()
  else await page.getByText('Einstellungen', { exact: true }).click()
  await page.getByRole('button', { name: 'Darstellung Hell', exact: true }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  expect(errors).toEqual([])
})
