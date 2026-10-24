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
        const formRow = page.getByRole('region', { name: /Pflichtspielform$/ }).first().locator('ol > li').first()
        await expect(formRow).toBeVisible()
        const rowLayout = await formRow.evaluate((row) => {
          const sides = [...row.querySelectorAll<HTMLElement>('[role="group"]')]
          const score = row.querySelector<HTMLElement>(':scope > div.grid > span:not([role="group"])')
          const box = (element: HTMLElement) => {
            const rect = element.getBoundingClientRect()
            return { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
          }
          return {
            sides: sides.map(box),
            score: score ? box(score) : null,
            nameWidths: sides.map((side) => side.querySelector<HTMLElement>(':scope > span:not([role="img"])')?.getBoundingClientRect().width ?? 0),
            crestBeforeName: sides.map((side) => {
              const crest = side.querySelector<HTMLElement>(':scope > img, :scope > [role="img"]')
              const name = side.querySelector<HTMLElement>(':scope > span:not([role="img"])')
              return crest && name ? crest.getBoundingClientRect().x < name.getBoundingClientRect().x : false
            }),
          }
        })
        expect(rowLayout.sides).toHaveLength(2)
        expect(rowLayout.score).not.toBeNull()
        if ((page.viewportSize()?.width ?? 1440) < 640) {
          expect(rowLayout.sides[1].y).toBeGreaterThan(rowLayout.sides[0].y)
          expect(Math.abs(rowLayout.sides[0].x - rowLayout.sides[1].x)).toBeLessThan(1)
          expect(rowLayout.score!.x).toBeGreaterThan(rowLayout.sides[0].x)
          expect(Math.min(...rowLayout.nameWidths)).toBeGreaterThanOrEqual(120)
          expect(rowLayout.crestBeforeName).toEqual([true, true])
        } else {
          const homeCenter = rowLayout.sides[0].y + rowLayout.sides[0].height / 2
          const awayCenter = rowLayout.sides[1].y + rowLayout.sides[1].height / 2
          expect(rowLayout.sides[0].x).toBeLessThan(rowLayout.score!.x)
          expect(rowLayout.score!.x).toBeLessThan(rowLayout.sides[1].x)
          expect(Math.abs(homeCenter - awayCenter)).toBeLessThan(1)
        }
      }
      if (route === 'match/ucl-long') await expect(page.getByRole('button', { name: 'Gemeinsamen Spieltipp speichern', exact: true })).toBeVisible()
      if (route === 'performance') await expect(page.getByRole('tab', { name: 'Gespeicherte Tipps', exact: true })).toBeVisible()
      if (route === '') await expect(page.getByText('Bayern Munich', { exact: true }).first()).toBeVisible()
      const assertFits = async (view: string) => {
        await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => resolve())))
        const overflow = await page.evaluate(() => {
          const width = document.documentElement.clientWidth
          return [...document.querySelectorAll<HTMLElement>('body *')].filter(element => {
            const box = element.getBoundingClientRect()
            return box.width > 0 && box.right > width + 1 && getComputedStyle(element).position !== 'absolute' && !element.closest('.overflow-x-auto')
          }).map(element => ({ tag: element.tagName, className: element.className, text: element.textContent?.slice(0, 90), right: Math.round(element.getBoundingClientRect().right) })).slice(0, 12)
        })
        expect(overflow, `${theme} /${route} ${view} must fit`).toEqual([])
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), `${route} ${view} page scroll width`).toBe(true)
      }
      await assertFits('default')
      await page.screenshot({ path: testInfo.outputPath(`${route.replaceAll('/', '-') || 'games'}-default.png`), fullPage: true })
      for (const tab of await page.getByRole('tab').all()) {
        const name = await tab.innerText()
        await tab.click()
        await assertFits(name)
      }
    }
  expect(errors).toEqual([])
  await page.goto('/#/team-form')
  await expect(page.getByText('4 von 4 ausgewählt')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('team-comparison.png'), fullPage: true })
})

test('mobile menu contains focus, closes with Escape and returns focus', async ({ page, api: _api }) => {
  test.skip((page.viewportSize()?.width ?? 1440) >= 1024, 'Desktop has separate analysis and settings menus')
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
  else await page.getByRole('button', { name: 'Einstellungen', exact: true }).click()
  await page.getByRole('button', { name: 'Darstellung Hell', exact: true }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  expect(errors).toEqual([])
})
