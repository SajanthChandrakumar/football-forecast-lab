import { test, expect, chooseCompetition, NOW } from './fixtures'

// Real production UI against deterministic API responses; no live shared tips are changed.
test('a new EPL fixture accepts its first tip and keeps it visible after reload', async ({ page, api }, testInfo) => {
  delete api.archive.epl2026['pl-next']
  await page.goto('/#/')
  await chooseCompetition(page, 'epl2026')
  await page.goto('/#/match/pl-next')
  await page.getByRole('spinbutton', { name: 'Tore Arsenal', exact: true }).fill('3')
  await page.getByRole('spinbutton', { name: 'Tore Chelsea', exact: true }).fill('1')
  await page.getByRole('button', { name: 'Gemeinsamen Spieltipp speichern', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: '3:1 gespeichert' })).toBeVisible()
  await page.reload()
  await expect(page.getByText('Gespeicherter gemeinsamer Tipp:')).toContainText('3:1')
  await page.getByRole('link', { name: 'Gemeinsame Tipps', exact: true }).filter({ visible: true }).click()
  const saved = page.getByRole('region', { name: 'Gespeicherte Tipps' })
  await expect(saved.getByText('Arsenal – Chelsea', { exact: true })).toBeVisible()
  await expect(saved.getByText('3:1', { exact: true })).toBeVisible()
  await page.reload()
  await expect(saved.getByText('3:1', { exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('saved-epl-tip.png') })
  await chooseCompetition(page, 'ucl2026')
  await expect(saved.getByText('Arsenal – Chelsea', { exact: true })).toHaveCount(0)
})

test('unarchived EPL fixtures appear among open tips and can be saved from the weekly view', async ({ page, api }) => {
  delete api.archive.epl2026['pl-next']
  await page.goto('/#/')
  await chooseCompetition(page, 'epl2026')
  await page.getByRole('button', { name: /Offene gemeinsame Tipps/ }).click()
  await expect(page.getByRole('spinbutton', { name: 'Tore Arsenal', exact: true })).toBeVisible()
  await page.getByRole('link', { name: 'Gemeinsame Tipps', exact: true }).filter({ visible: true }).click()
  await expect(page.getByRole('heading', { name: 'Tipps & Auswertung', exact: true })).toBeVisible()
  await page.getByText('Tipps bearbeiten', { exact: false }).first().click()
  await page.getByLabel('Tipp für Arsenal gegen Chelsea', { exact: true }).fill('0:0')
  await page.getByRole('button', { name: /Tipp.*speichern/ }).click()
  await expect(page.getByRole('region', { name: 'Gespeicherte Tipps' }).getByText('0:0', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('region', { name: 'Gespeicherte Tipps' }).getByText('0:0', { exact: true })).toBeVisible()
})

test('a saved tip awaiting a result remains visible without being counted as completed', async ({ page, api }) => {
  const entry = api.archive.epl2026['pl-next']
  entry.prediction.user_tip = '1:1'
  entry.metadata.commence_time = new Date(NOW.getTime() - 3 * 60 * 60_000).toISOString()
  await page.goto('/#/performance')
  await chooseCompetition(page, 'epl2026')
  const saved = page.getByRole('region', { name: 'Gespeicherte Tipps' })
  await expect(saved.getByText('1:1', { exact: true })).toBeVisible()
  await expect(saved.getByText('Ergebnis ausstehend', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Abgeschlossene Spiele', exact: true })).toBeVisible()
  await expect(saved.getByText(/Punkte/)).toHaveCount(0)
})


test('a failed archive refresh retains a weekly draft and prevents blind saving', async ({ page, api }) => {
  await page.goto('/#/performance')
  await chooseCompetition(page, 'epl2026')
  await expect(page.getByRole('heading', { name: 'Tipps & Auswertung', exact: true })).toBeVisible()
  await page.getByText('Tipps bearbeiten', { exact: false }).first().click()
  const draft = page.getByLabel('Tipp für Arsenal gegen Chelsea', { exact: true })
  await draft.fill('0:0')
  api.failArchive = true
  const mobile = (page.viewportSize()?.width ?? 1440) < 1024
  if (mobile) await page.getByRole('button', { name: 'Mehr', exact: true }).click()
  else await page.getByText('Einstellungen', { exact: true }).click()
  await page.getByRole('button', { name: 'Gespeicherte Daten neu laden', exact: true }).filter({ visible: true }).click()
  if (mobile) await page.getByRole('button', { name: 'Menü schliessen' }).click()
  await expect(page.getByText('Gespeicherte Tipps konnten nicht geladen werden. Speichern ist pausiert, damit vorhandene Tipps nicht überschrieben werden.', { exact: true })).toBeVisible({ timeout: 15000 })
  await expect(page.getByRole('button', { name: /Tipp.*speichern/ })).toBeDisabled()
  await expect(draft).toHaveValue('0:0')
  expect(api.saves).toHaveLength(0)
})
