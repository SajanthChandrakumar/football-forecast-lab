import { NOW, test, expect, enterEditorKey } from './fixtures'

test('club detail reads one canonical game and keeps core tip evidence independent of analysis', async ({ page, api }) => {
  await page.addInitScript(() => localStorage.setItem('competition', 'ucl2026'))
  let releaseAnalysis!: () => void
  api.analysisGate = new Promise<void>(resolve => { releaseAnalysis = resolve })
  const matchRequests: URL[] = []
  page.on('request', request => {
    const url = new URL(request.url())
    if (url.pathname.startsWith('/api/matches')) matchRequests.push(url)
  })

  await page.goto('/#/match/ucl-alias')
  await expect(page.getByRole('heading', { name: /Bayern Munich.*Arsenal/ })).toBeVisible()
  await expect(page.getByText('2:1', { exact: true }).first()).toBeVisible()
  await expect(page.getByRole('img', { name: /Spielausgangschancen: Bayern Munich 50%/ })).toBeVisible()
  await expect.poll(() => api.coreRequests.some(request => request.competition === 'ucl2026' && request.matchId === 'ucl-next')).toBe(true)

  expect(matchRequests.some(url => url.pathname === '/api/matches')).toBe(false)
  expect(matchRequests.some(url => url.pathname === '/api/matches/ucl-alias')).toBe(true)
  expect(api.analysisRequests).toHaveLength(0)
  expect(api.archiveMatchRequests).toContainEqual({ competition: 'ucl2026', matchId: 'ucl-next' })

  await page.getByRole('tab', { name: 'Form', exact: true }).click()
  await expect.poll(() => api.analysisRequests.length).toBe(1)
  await expect(page.getByRole('region', { name: 'Zuletzt gespeicherte Spielprognose', exact: true })).toContainText('2:1')
  await expect(page.getByRole('img', { name: /Spielausgangschancen: Bayern Munich 50%/ })).toBeVisible()
  releaseAnalysis()
  await expect(page.getByRole('region', { name: 'Bayern Munich Pflichtspielform', exact: true })).toContainText('1 von 10')
})

test('failed club analysis stays distinct from missing form and can be retried', async ({ page, api }) => {
  await page.addInitScript(() => localStorage.setItem('competition', 'ucl2026'))
  api.analysisFailureCount = 1

  await page.goto('/#/match/ucl-next')
  await expect(page.getByText('2:1', { exact: true }).first()).toBeVisible()
  await page.getByRole('tab', { name: 'Form', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText(/Zusätzliche Spieldetails konnten nicht geladen werden/)
  await expect(page.getByRole('button', { name: /erneut laden|erneut versuchen/i })).toBeVisible()

  await page.getByRole('button', { name: /erneut laden|erneut versuchen/i }).click()
  await expect(page.getByRole('region', { name: 'Bayern Munich Pflichtspielform', exact: true })).toContainText('1 von 10')
  expect(api.analysisRequests.length).toBeGreaterThanOrEqual(2)
})

test('a newer analysis version refreshes core before its detail can replace the match', async ({ page, api }) => {
  await page.addInitScript(() => localStorage.setItem('competition', 'ucl2026'))
  api.analysisVersions.push('fixture-view-v2')
  api.promoteAnalysisVersion = true

  await page.goto('/#/match/ucl-next')
  await page.getByRole('tab', { name: 'Form', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Bayern Munich Pflichtspielform', exact: true })).toContainText('1 von 10')

  expect(api.coreRequests.length).toBeGreaterThanOrEqual(2)
  expect(api.analysisResponseVersions).toEqual(['fixture-view-v2', 'fixture-view-v2'])
})

test('overview and core 202 responses poll until the prepared records are ready', async ({ page, api }) => {
  api.overviewProcessingResponses = 1
  api.coreProcessingResponses = 1
  const overviewRequests: URL[] = []
  page.on('request', request => {
    const url = new URL(request.url())
    if (url.pathname === '/api/matches') overviewRequests.push(url)
  })

  await page.goto('/#/')
  await expect(page.getByRole('link', { name: 'Tipp ansehen: Bayern Munich gegen Arsenal', exact: true })).toBeVisible()
  expect(overviewRequests.length).toBeGreaterThanOrEqual(2)
  expect(overviewRequests.every(url => url.searchParams.get('overview') === 'true')).toBe(true)

  await page.goto('/#/match/ucl-next')
  await expect(page.getByText('2:1', { exact: true }).first()).toBeVisible()
  expect(api.coreRequests.length).toBeGreaterThanOrEqual(2)
})

test('last-good overview and core rows identify stored data that is still refreshing', async ({ page, api }) => {
  api.viewStatus = 'refreshing'
  await page.goto('/#/')
  await expect(page.getByRole('status').filter({ hasText: 'Neue gespeicherte Daten werden übernommen' })).toBeVisible()
  await page.goto('/#/match/ucl-next')
  await expect(page.getByRole('status').filter({ hasText: 'Neue gespeicherte Daten werden übernommen' })).toBeVisible()
})

test('persistent 202 responses stop after bounded polls and a retry starts a new poll window', async ({ page, api }) => {
  api.overviewProcessingResponses = 20
  await page.goto('/#/')
  await expect.poll(() => api.matchRequests.filter(request => request.overview).length).toBe(4)
  await expect(page.getByRole('button', { name: 'Erneut versuchen', exact: true })).toBeVisible()
  const overviewCount = api.matchRequests.filter(request => request.overview).length
  await page.waitForTimeout(350)
  expect(api.matchRequests.filter(request => request.overview)).toHaveLength(overviewCount)
  await page.getByRole('button', { name: 'Erneut versuchen', exact: true }).click()
  await expect.poll(() => api.matchRequests.filter(request => request.overview).length).toBeGreaterThan(overviewCount)

  api.coreProcessingResponses = 20
  await page.goto('/#/match/ucl-next')
  await expect.poll(() => api.coreRequests.length).toBe(4)
  await expect(page.getByRole('button', { name: 'Erneut versuchen', exact: true })).toBeVisible()
  const coreCount = api.coreRequests.length
  await page.waitForTimeout(350)
  expect(api.coreRequests).toHaveLength(coreCount)
  await page.getByRole('button', { name: 'Erneut versuchen', exact: true }).click()
  await expect.poll(() => api.coreRequests.length).toBeGreaterThan(coreCount)
})

test('a successful club tip save immediately updates a cached full-archive view', async ({ page, api }) => {
  await page.addInitScript(() => localStorage.setItem('competition', 'epl2026'))
  await page.goto('/#/')
  await page.getByRole('combobox', { name: 'Spiele filtern', exact: true }).selectOption('tips')
  await expect(page.getByRole('spinbutton', { name: 'Tore Arsenal', exact: true })).toBeVisible()
  await page.goto('/#/match/pl-next')
  await expect(page.getByRole('spinbutton', { name: 'Tore Arsenal', exact: true })).toBeVisible()

  let releaseArchive!: () => void
  api.archiveGate = new Promise<void>(resolve => { releaseArchive = resolve })
  api.requireEditorKey = true
  await page.getByRole('spinbutton', { name: 'Tore Arsenal', exact: true }).fill('3')
  await page.getByRole('spinbutton', { name: 'Tore Chelsea', exact: true }).fill('1')
  await page.getByRole('button', { name: 'Gemeinsamen Spieltipp speichern', exact: true }).click()
  await enterEditorKey(page, api.validEditorKey)
  await expect(page.getByRole('status').filter({ hasText: '3:1 gespeichert' })).toBeVisible()

  await page.goto('/#/')
  await page.getByRole('combobox', { name: 'Spiele filtern', exact: true }).selectOption('upcoming')
  const row = page.locator('article.match-card').filter({ has: page.getByRole('link', { name: 'Tipp ansehen: Arsenal gegen Chelsea', exact: true }) }).first()
  await expect(row).toContainText('Gemeinsamer Tipp: 3:1')
  releaseArchive()
})


test('an open form view adopts new cached form data with an unchanged core version', async ({ page, api }) => {
  await page.clock.install({ time: NOW })
  await page.goto('/#/match/ucl-next?view=form')
  const form = page.getByRole('region', { name: 'Bayern Munich Pflichtspielform', exact: true })
  await expect(form).toContainText('2:1')
  const priorRequests = api.analysisRequests.length
  const entry = api.matches.ucl2026[0].home_form!.matches![0]
  Object.assign(entry, { score: '3:0', goals_for: 3, goals_against: 0 })
  await page.clock.fastForward(61_000)
  await expect.poll(() => api.analysisRequests.length).toBeGreaterThan(priorRequests)
  await expect(form).toContainText('3:0')
})

test('completed model details never substitute live matrices or bot tips for missing archived chances', async ({ page, api }) => {
  const match = api.matches.ucl2026[0]
  match.completed = true
  match.actual_score = '1:0'
  match.bots = { broker: { tip: '8:0' } }
  match.matrix = { '8': { '0': .8 }, '0': { '0': .2 } }
  const archived = api.archive.ucl2026[match.id]
  archived.post_match_result = { status: 'completed', actual_score: '1:0' }
  archived.prediction.top_tip = '0:1'
  archived.prediction.model_tip = '0:1'
  delete archived.prediction.probabilities
  await page.goto('/#/match/ucl-next?view=model')
  await expect.poll(() => api.analysisRequests.length).toBeGreaterThan(0)
  await expect(page.getByRole('heading', { name: 'Ergebnis-Alternativen', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Bot-Vorschläge', exact: true })).toHaveCount(0)
  await expect(page.getByText('Für die Ergebnistabelle sind keine Daten verfügbar.', { exact: true })).toBeVisible()
  await expect(page.getByText('8:0', { exact: true })).toHaveCount(0)
})
