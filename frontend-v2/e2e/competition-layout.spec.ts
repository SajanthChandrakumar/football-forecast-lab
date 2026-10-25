import { test, expect } from './fixtures'

const competitions = [
  { id: 'wc2026', name: 'WM', match: 'wc-next' },
  { id: 'ucl2026', name: 'UCL', match: 'ucl-long' },
  { id: 'epl2026', name: 'PL', match: 'pl-next' },
] as const

for (const competition of competitions) {
  for (const appearance of ['light', 'dark'] as const) {
    test(`${competition.name} ${appearance}: every view and analysis tab remains readable`, async ({ page, api: _api }, testInfo) => {
      test.setTimeout(120_000)
      const errors: string[] = []
      page.on('pageerror', error => errors.push(error.message))
      await page.addInitScript(({ id, appearance }) => {
        localStorage.setItem('competition', id)
        localStorage.setItem('theme', appearance)
      }, { id: competition.id, appearance })
      const routes = ['', `match/${competition.match}`, 'groups', 'data-sources', 'team-form', 'value-bets', 'edge', 'performance', ...(competition.id === 'epl2026' ? [] : ['simulator'])]
      const fits = async (where: string) => {
        await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))))
        const outside = await page.evaluate(() => {
          const width = document.documentElement.clientWidth
          return [...document.querySelectorAll<HTMLElement>('main *')].filter(element => {
            const box = element.getBoundingClientRect()
            return box.width > 0 && box.right > width + 1 && getComputedStyle(element).position !== 'absolute'
              && !element.closest('.overflow-x-auto')
          }).map(element => ({ tag: element.tagName, text: element.textContent?.slice(0, 70), right: Math.round(element.getBoundingClientRect().right) })).slice(0, 8)
        })
        expect(outside, where).toEqual([])
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), where).toBe(true)
        for (const tab of await page.getByRole('tab').all()) {
          expect(await tab.evaluate(element => element.scrollWidth <= element.clientWidth + 1), `${where}: tab label fits`).toBe(true)
        }
      }
      for (const route of routes) {
        await page.goto(`/#/${route}`)
        await expect(page.locator('main h1')).toBeVisible()
        await expect(page.locator('main .animate-pulse').filter({ visible: true })).toHaveCount(0)
        await expect(page.locator('html')).toHaveAttribute('data-theme', appearance)
        await expect(page.locator('html')).toHaveAttribute('data-competition', competition.id)
        await expect(page.getByRole('banner').getByRole('button', { name: competition.name, exact: true })).toHaveAttribute('aria-pressed', 'true')
        await fits(route || 'games')
        await page.screenshot({ path: testInfo.outputPath(`${competition.id}-${appearance}-${route.replaceAll('/', '-') || 'games'}.png`), fullPage: true })
        for (const tab of await page.getByRole('tab').all()) {
          const label = await tab.innerText()
          await tab.click()
          await expect(page.locator('main .animate-pulse').filter({ visible: true })).toHaveCount(0)
          await fits(`${route}: ${label}`)
        }
      }
      expect(errors).toEqual([])
    })
  }
}
