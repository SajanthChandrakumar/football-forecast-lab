import { expect, NOW, test } from './fixtures'

for (const appearance of ['light', 'dark'] as const) {
  test(`recorded odds chart keeps units, outcome legend and observations readable in ${appearance}`, async ({ page, api: _api }, testInfo) => {
    await page.addInitScript(value => localStorage.setItem('theme', value), appearance)
    await page.route('**/api/odds-history/**', route => route.fulfill({ json: {
      match_id: 'ucl-next', competition: 'ucl2026', status: 'available',
      probability_change_pp: { home: 3, draw: -2, away: -1 },
      observations: [
        { observed_at: new Date(NOW.getTime() - 86_400_000).toISOString(), bucket: 't24h', source: 'odds_api', odds: { home: 2.1, draw: 3.5, away: 3.1 }, probabilities: { home: .47, draw: .29, away: .24 } },
        { observed_at: NOW.toISOString(), bucket: 't6h', source: 'odds_api', odds: { home: 1.9, draw: 3.4, away: 4.2 }, probabilities: { home: .5, draw: .27, away: .23 } },
      ],
    } }))
    await page.goto('/#/match/ucl-next?view=market')
    await page.locator('summary').filter({ hasText: 'Wie haben sich die Quoten verändert?' }).click()
    const chart = page.getByRole('img', { name: 'Bereinigte 1X2-Wahrscheinlichkeit für Bayern Munich, Remis und Arsenal', exact: true })
    await expect(chart).toBeVisible()
    await expect(chart.getByText('Wahrscheinlichkeit', { exact: true })).toBeVisible()
    for (const outcome of ['Heim', 'Remis', 'Auswärts']) await expect(chart.getByText(outcome, { exact: true })).toBeVisible()
    await expect(page.getByRole('list', { name: 'Gespeicherte Quotenpunkte' }).locator('li')).toHaveCount(2)
    const unitBox = await chart.getByText('Wahrscheinlichkeit', { exact: true }).boundingBox()
    const chartBox = await chart.boundingBox()
    expect(chartBox).not.toBeNull()
    expect(unitBox?.x).toBeGreaterThanOrEqual(chartBox!.x)
    const topTick = await chart.getByText('100%', { exact: true }).boundingBox()
    expect(topTick?.x).toBeGreaterThanOrEqual(chartBox!.x)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath(`recorded-odds-${appearance}.png`), fullPage: true })
  })
}
