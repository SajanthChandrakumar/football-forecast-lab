import { test, expect } from './fixtures'

for (const competition of ['epl2026', 'ucl2026'] as const) {
  test(`${competition} home loads only the overview and opens full details on demand`, async ({ page, api }) => {
    await page.addInitScript(mode => localStorage.setItem('competition', mode), competition)
    const requests: URL[] = []
    page.on('request', request => {
      const url = new URL(request.url())
      if (url.pathname.startsWith('/api/')) requests.push(url)
    })
    await page.route('**/api/matches?*', route => {
      if (new URL(route.request().url()).searchParams.get('overview') !== 'true') return route.fallback()
      return route.fulfill({ json: api.matches[competition].map(match => {
        const row = { ...match, detail_level: 'overview' as const }; delete row.home_form; delete row.away_form; delete row.matrix; delete row.match_intelligence; return row
      }) })
    })
    await page.goto('/#/')
    const match = api.matches[competition][0]
    const link = page.getByRole('link', { name: `Tipp ansehen: ${match.home_team} gegen ${match.away_team}`, exact: true })
    await expect(link).toBeVisible()
    const matchRequests = () => requests.filter(url => url.pathname === '/api/matches')
    expect(matchRequests()).toHaveLength(1)
    expect(matchRequests()[0].searchParams.get('overview')).toBe('true')
    expect(requests.some(url => url.pathname === '/api/archive')).toBe(false)
    await link.click()
    await expect(page.getByRole('tab', { name: 'Form', exact: true })).toBeVisible()
    await expect.poll(() => matchRequests().length).toBe(2)
    expect(matchRequests()[1].searchParams.has('overview')).toBe(false)
    await page.getByRole('tab', { name: 'Form', exact: true }).click()
    await expect(page.getByRole('region', { name: `${match.home_team} Pflichtspielform`, exact: true })).toContainText('1 von 10')
  })

  test(`${competition} shared tips load their archive when selected`, async ({ page, api: _api }) => {
    await page.addInitScript(mode => localStorage.setItem('competition', mode), competition)
    const requests: string[] = []
    page.on('request', request => requests.push(new URL(request.url()).pathname))
    await page.goto('/#/')
    await expect(page.getByRole('heading', { name: 'Spiele & Tipps', exact: true })).toBeVisible()
    expect(requests).not.toContain('/api/archive')
    await page.getByRole('combobox', { name: 'Spiele filtern', exact: true }).selectOption('tips')
    await expect.poll(() => requests.filter(path => path === '/api/archive').length).toBe(1)
    await expect(page.getByText('Gemeinsame Tipps · Für alle sichtbar · Abgabe bis T−5', { exact: true })).toBeVisible()
    await expect(page.getByRole('spinbutton', { name: /Tore/ }).first()).toBeVisible()
  })
}


test('saved-data reload updates the active club overview immediately', async ({ page, api }) => {
  const overviewRequests: string[] = []
  page.on('request', request => { if (request.url().includes('overview=true')) overviewRequests.push(request.url()) })
  await page.goto('/#/')
  const row = page.locator('article.match-card').filter({ has: page.getByRole('link', { name: 'Tipp ansehen: Bayern Munich gegen Arsenal', exact: true }) }).first()
  await expect(row).toContainText('2:1')
  api.matches.ucl2026[0].top_tip = '4:0'
  const mobile = (page.viewportSize()?.width ?? 1440) < 1024
  await page.getByRole('button', { name: mobile ? 'Mehr' : 'Einstellungen', exact: true }).click()
  await page.getByRole('button', { name: 'Gespeicherte Daten neu laden', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Gespeicherte Daten neu laden', exact: true })).toBeEnabled()
  await page.keyboard.press('Escape')
  await expect.poll(() => overviewRequests.length).toBe(2)
  await expect(row).toContainText('4:0')
})
