import { test, expect, NOW, fixture } from './fixtures'

test('match analysis tabs keep the prediction evidence and tip editor available on a phone', async ({ page, api }, testInfo) => {
  test.skip(testInfo.project.name !== 'phone-375', 'The first-screen save requirement is specific to the 375px phone viewport.')

  api.prediction = {
    model_tip: '3:0',
    probabilities: { home: 0.62, draw: 0.25, away: 0.13 },
    source_mode: 'elo-only',
    status: 'fresh',
    observed_at: NOW.toISOString(),
    input_provenance: { elo: { status: 'fresh', source: 'clubelo', observed_at: NOW.toISOString() } },
  }

  await page.goto('/#/match/ucl-next')
  const tabs = page.getByRole('tablist', { name: 'Spielanalyse' })
  const overviewTab = tabs.getByRole('tab', { name: 'Überblick', exact: true })
  await expect(overviewTab).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByText('62%', { exact: true })).toBeVisible()
  await expect(page.getByText('25%', { exact: true })).toBeVisible()
  await expect(page.getByText('13%', { exact: true })).toBeVisible()
  await expect(page.getByText('Elo-Modell', { exact: false }).first()).toBeVisible()

  await page.getByRole('spinbutton', { name: 'Tore Bayern Munich', exact: true }).fill('4')
  await page.getByRole('spinbutton', { name: 'Tore Arsenal', exact: true }).fill('3')

  const saveButton = page.getByRole('button', { name: 'Gemeinsamen Spieltipp speichern', exact: true })
  const saveBox = await saveButton.boundingBox()
  const mobileNavBox = await page.getByRole('navigation', { name: 'Hauptnavigation' }).last().boundingBox()
  expect(saveBox).not.toBeNull()
  expect(mobileNavBox).not.toBeNull()
  expect(saveBox!.y + saveBox!.height).toBeLessThanOrEqual(mobileNavBox!.y)

  await tabs.getByRole('tab', { name: 'Form', exact: true }).click()
  await expect(tabs.getByRole('tab', { name: 'Form', exact: true })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('heading', { name: 'Tore & Form', exact: true })).toBeVisible()
  await tabs.getByRole('tab', { name: 'Aufstellungen', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Aufstellungen & Spieler', exact: true })).toBeVisible()
  await tabs.getByRole('tab', { name: 'Markt', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Aktuelle Quoten', exact: true })).toBeVisible()
  await tabs.getByRole('tab', { name: 'Modelldaten', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Ergebnis-Alternativen', exact: true })).toBeVisible()

  await overviewTab.click()
  await expect(page.getByRole('spinbutton', { name: 'Tore Bayern Munich', exact: true })).toHaveValue('4')
  await expect(page.getByRole('spinbutton', { name: 'Tore Arsenal', exact: true })).toHaveValue('3')

  await page.goBack()
  await expect(tabs.getByRole('tab', { name: 'Modelldaten', exact: true })).toHaveAttribute('aria-selected', 'true')
  await overviewTab.click()
  await expect(page.getByRole('spinbutton', { name: 'Tore Bayern Munich', exact: true })).toHaveValue('4')
})

test('club outcome chances and score matrices state their different time basis', async ({ page, api }, testInfo) => {
  test.skip(testInfo.project.name !== 'phone-375', 'The time-basis labels need one representative phone run.')
  api.prediction = {
    model_tip: '1:0',
    probabilities: { home: .52, draw: .28, away: .2 },
    probability_basis: 'regulation',
    matrix: { 1: { 0: .12, 1: .15 }, 2: { 0: .08, 1: .1 } },
    matrix_basis: 'after_extra_time',
    source_mode: 'elo-only',
    status: 'fresh',
    observed_at: NOW.toISOString(),
  }

  await page.goto('/#/match/ucl-next')
  await expect(page.getByRole('heading', { name: 'Sieg, Remis, Niederlage nach 90 Minuten' })).toBeVisible()
  await page.getByRole('tab', { name: 'Modelldaten', exact: true }).click()
  await expect(page.getByText('Einzelne Spielstände laut Score-Matrix (inklusive Verlängerung, ohne Elfmeterschiessen)', { exact: true })).toBeVisible()
})

test('completed club detail keeps its archived tip when an older live prediction finishes late', async ({ page, api }) => {
  const completed = fixture('ucl-old', 'Bayern Munich', 'Arsenal', -86_400_000)
  api.matches.ucl2026.push(completed)
  const archived = structuredClone(api.archive.ucl2026['ucl-next'])
  archived.metadata = { ...archived.metadata, home_team: completed.home_team, away_team: completed.away_team, commence_time: completed.raw_match?.commence_time }
  archived.prediction = { ...archived.prediction, model_tip: '0:2', top_tip: '0:2', frozen_at: new Date(NOW.getTime() - 2 * 86_400_000).toISOString() }
  api.archive.ucl2026['ucl-old'] = archived

  let releasePrediction!: () => void
  api.predictionGate = new Promise<void>((resolve) => { releasePrediction = resolve })
  await page.goto('/#/match/ucl-next')
  await expect.poll(() => api.predictionRequests.map(({ matchId }) => matchId)).toEqual(['ucl-next'])

  await page.evaluate(() => { window.location.hash = '/match/ucl-old' })
  await expect(page).toHaveURL(/#\/match\/ucl-old$/)
  const recommendation = page.getByRole('region', { name: 'Empfohlener Ergebnistipp' })
  await expect(recommendation).toContainText('0:2')
  expect(api.predictionRequests.map(({ matchId }) => matchId)).toEqual(['ucl-next'])

  releasePrediction()
  await expect.poll(() => api.predictionResponses).toBe(1)
  await expect(recommendation).toContainText('0:2')
  expect(api.predictionRequests.map(({ matchId }) => matchId)).toEqual(['ucl-next'])
})
