import { test, expect, NOW } from './fixtures'

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
