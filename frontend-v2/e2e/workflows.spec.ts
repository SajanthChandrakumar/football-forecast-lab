import { test, expect, chooseCompetition, fixture, NOW } from './fixtures'

const saveButton = (page: import('@playwright/test').Page) => page.getByRole('button', { name: 'Gemeinsamen Spieltipp speichern', exact: true })

async function enterTip(page: import('@playwright/test').Page, home = '4', away = '3') {
  await page.getByRole('spinbutton', { name: 'Tore Bayern Munich', exact: true }).fill(home)
  await page.getByRole('spinbutton', { name: 'Tore Arsenal', exact: true }).fill(away)
}

test('a rejected save preserves input and a successful retry survives reload', async ({ page, api }) => {
  api.failSave = 503
  await page.goto('/#/match/ucl-next')
  await enterTip(page)
  await saveButton(page).click()
  await expect(page.getByRole('alert').filter({ hasText: 'Der Tipp konnte nicht gespeichert werden' })).toBeVisible()
  await expect(page.getByRole('spinbutton', { name: 'Tore Bayern Munich', exact: true })).toHaveValue('4')
  await expect(page.getByRole('spinbutton', { name: 'Tore Arsenal', exact: true })).toHaveValue('3')
  expect(api.archive.ucl2026['ucl-next'].prediction.user_tip).toBeNull()
  api.failSave = 0
  await saveButton(page).click()
  await expect(page.getByRole('status').filter({ hasText: '4:3 gespeichert' })).toBeVisible()
  expect(api.saves).toEqual(Array(2).fill({ match_id: 'ucl-next', user_tip: '4:3', competition: 'ucl2026' }))
  await page.reload()
  await expect(page.getByText('Gespeicherter gemeinsamer Tipp:')).toContainText('4:3')
  await expect(page.getByRole('spinbutton', { name: 'Tore Bayern Munich', exact: true })).toHaveValue('4')
})

test('a server cutoff rejection closes the editor', async ({ page, api }) => {
  api.failSave = 409
  await page.goto('/#/match/ucl-next')
  await enterTip(page)
  await saveButton(page).click()
  await expect(page.getByRole('alert').filter({ hasText: 'fünf Minuten vor Anpfiff geschlossen' })).toBeVisible()
  await expect(saveButton(page)).toBeDisabled()
  await expect(page.getByRole('spinbutton', { name: 'Tore Bayern Munich', exact: true })).toHaveAttribute('readonly', '')
  expect(api.saves).toHaveLength(1)
})

test('a fixture more than a month away remains editable', async ({ page, api }) => {
  api.matches.ucl2026[0] = fixture('ucl-next', 'Bayern Munich', 'Arsenal', 60 * 86_400_000)
  await page.goto('/#/match/ucl-next')
  await enterTip(page)
  await saveButton(page).click()
  await expect(page.getByRole('status').filter({ hasText: '4:3 gespeichert' })).toBeVisible()
})

test('the editor closes at T−5 without requiring navigation', async ({ page, api }) => {
  await page.clock.install({ time: NOW })
  api.matches.ucl2026[0] = fixture('ucl-next', 'Bayern Munich', 'Arsenal', 6 * 60_000)
  await page.goto('/#/match/ucl-next')
  await enterTip(page)
  await expect(saveButton(page)).toBeEnabled()
  await page.clock.fastForward(61_000)
  await expect(saveButton(page)).toBeDisabled()
  await expect(page.getByRole('spinbutton', { name: 'Tore Bayern Munich', exact: true })).toHaveValue('4')
  expect(api.saves).toHaveLength(0)
})

test('an unavailable archive cannot silently overwrite an existing tip', async ({ page, api }) => {
  api.failArchive = true
  api.archive.ucl2026['ucl-next'].prediction.user_tip = '1:0'
  await page.goto('/#/match/ucl-next')
  await expect(page.getByRole('alert').filter({ hasText: 'Gemeinsame Tipps konnten nicht geladen werden' })).toBeVisible()
  await expect(saveButton(page)).toHaveCount(0)
  api.failArchive = false
  await page.getByRole('button', { name: 'Tipps erneut laden' }).click()
  await expect(page.getByRole('spinbutton', { name: 'Tore Bayern Munich', exact: true })).toHaveValue('1')
  await expect(page.getByRole('spinbutton', { name: 'Tore Arsenal', exact: true })).toHaveValue('0')
  expect(api.saves).toHaveLength(0)
})

test('a failed historical lineup request is distinct from missing data and can retry', async ({ page, api }) => {
  api.failHistory = true
  await page.goto('/#/match/ucl-next')
  await page.locator('summary').filter({ hasText: 'Weitere Daten zur Analyse' }).click()
  await page.getByRole('button', { name: 'Aufstellung ansehen', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'Aufstellung konnte nicht geladen werden' })).toBeVisible()
  api.failHistory = false
  await page.getByRole('button', { name: 'Aufstellung erneut laden' }).click()
  await expect(page.getByText('Diese historische Aufstellung ist noch nicht archiviert.', { exact: false })).toBeVisible()
})

test('a pending save stays in its competition when the competition changes', async ({ page, api }) => {
  let finishSave!: () => void
  api.saveGate = new Promise<void>(resolve => { finishSave = resolve })
  await page.goto('/#/match/ucl-next')
  await enterTip(page)
  await saveButton(page).click()
  await expect(page.getByRole('button', { name: 'Speichert …', exact: true })).toBeDisabled()
  await chooseCompetition(page, 'epl2026')
  finishSave()
  await expect.poll(() => api.archive.ucl2026['ucl-next'].prediction.user_tip).toBe('4:3')
  expect(api.saves[0].competition).toBe('ucl2026')
  expect(api.archive.epl2026['pl-next'].prediction.user_tip).toBeNull()
  await page.goto('/#/match/pl-next')
  await expect(page.getByRole('spinbutton', { name: 'Tore Chelsea', exact: true })).toHaveValue('')
})

test('team comparison persists, respects four teams, and is scoped by competition', async ({ page, api: _api }) => {
  await page.goto('/#/match/ucl-next')
  await page.getByRole('button', { name: 'Diese Teams vergleichen' }).click()
  const selected = page.getByRole('group', { name: 'Ausgewählte Teams' })
  await expect(selected).toContainText('Bayern Munich')
  await expect(selected).toContainText('Arsenal')
  await page.getByRole('button', { name: 'Paris Saint-Germain', exact: true }).click()
  await page.getByRole('button', { name: 'Liverpool', exact: true }).click()
  await expect(page.getByText('4 von 4 ausgewählt')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Borussia Mönchengladbach', exact: true })).toBeDisabled()
  await page.reload()
  await expect(selected.getByRole('button')).toHaveCount(4)
  await chooseCompetition(page, 'epl2026')
  await expect(selected).toContainText('Chelsea')
  await expect(selected).not.toContainText('Bayern Munich')
  await chooseCompetition(page, 'ucl2026')
  await expect(selected.getByRole('button')).toHaveCount(4)
  for (const team of ['Bayern Munich', 'Arsenal', 'Paris Saint-Germain', 'Liverpool']) await page.getByRole('button', { name: `${team} aus dem Vergleich entfernen`, exact: true }).click()
  await expect(page.getByText('0 von 4 ausgewählt')).toBeVisible()
  await page.reload()
  await expect(page.getByText('0 von 4 ausgewählt')).toBeVisible()
})

test('a slow response exposes loading and then the fixture list', async ({ page, api }) => {
  let finishLoad!: () => void
  api.matchesGate = new Promise<void>(resolve => { finishLoad = resolve })
  await page.goto('/#/')
  await expect(page.getByRole('status', { name: 'Spiele werden geladen' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Spielanalyse öffnen', exact: false })).toHaveCount(0)
  finishLoad()
  await expect(page.getByText('Bayern Munich', { exact: true }).first()).toBeVisible()
})

test('an unavailable refresh keeps known fixtures and reports the failure', async ({ page, api }) => {
  await page.goto('/#/')
  await expect(page.getByText('Bayern Munich', { exact: true }).first()).toBeVisible()
  api.unavailableRefresh = true
  if ((page.viewportSize()?.width ?? 1440) < 1024) await page.getByRole('button', { name: 'Mehr', exact: true }).click()
  else await page.getByText('Einstellungen', { exact: true }).click()
  await page.getByRole('button', { name: 'Gespeicherte Daten neu laden', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'Daten konnten nicht neu geladen werden' })).toBeVisible()
  if ((page.viewportSize()?.width ?? 1440) < 1024) await page.getByRole('button', { name: 'Menü schliessen' }).click()
  await expect(page.getByText('Bayern Munich', { exact: true }).first()).toBeVisible()
})

test('a pending refresh cannot replace another competition’s cached fixtures', async ({ page, api }) => {
  await page.goto('/#/')
  await expect(page.getByText('Bayern Munich', { exact: true }).first()).toBeVisible()
  await chooseCompetition(page, 'epl2026')
  await expect(page.getByText('Chelsea', { exact: true }).first()).toBeVisible()
  await chooseCompetition(page, 'ucl2026')
  api.archive.ucl2026['ucl-next'].prediction.user_tip = '0:1'
  let finishLoad!: () => void
  api.matchesGate = new Promise<void>(resolve => { finishLoad = resolve })
  const mobile = (page.viewportSize()?.width ?? 1440) < 1024
  if (mobile) await page.getByRole('button', { name: 'Mehr', exact: true }).click()
  else await page.getByText('Einstellungen', { exact: true }).click()
  await page.getByRole('button', { name: 'Gespeicherte Daten neu laden', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Wird geladen…', exact: true })).toBeDisabled()
  await page.getByLabel('Wettbewerb', { exact: true }).filter({ visible: true }).selectOption('epl2026')
  finishLoad()
  await expect(page.getByRole('status').filter({ hasText: 'Gespeicherte Daten für UCL 2026/27 geladen.' })).toBeVisible()
  if (mobile) await page.getByRole('button', { name: 'Menü schliessen' }).click()
  await expect(page.getByText('Chelsea', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('Bayern Munich', { exact: true })).toHaveCount(0)
  await chooseCompetition(page, 'ucl2026')
  await page.goto('/#/match/ucl-next')
  await expect(page.getByRole('spinbutton', { name: 'Tore Bayern Munich', exact: true })).toHaveValue('0')
  await expect(page.getByRole('spinbutton', { name: 'Tore Arsenal', exact: true })).toHaveValue('1')
})
