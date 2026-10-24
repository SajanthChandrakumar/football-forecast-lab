import { test, expect, chooseCompetition, enterEditorKey, fixture, NOW } from './fixtures'

// Real production UI against deterministic API responses; no live shared tips are changed.
test('a new EPL fixture accepts its first tip and keeps it visible after reload', async ({ page, api }, testInfo) => {
  delete api.archive.epl2026['pl-next']
  await page.goto('/#/')
  await chooseCompetition(page, 'epl2026')
  await page.goto('/#/match/pl-next')
  await page.getByRole('spinbutton', { name: 'Tore Arsenal', exact: true }).fill('3')
  await page.getByRole('spinbutton', { name: 'Tore Chelsea', exact: true }).fill('1')
  await page.getByRole('button', { name: 'Gemeinsamen Spieltipp speichern', exact: true }).click()
  await enterEditorKey(page, api.validEditorKey)
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
  await page.getByRole('combobox', { name: 'Spiele filtern' }).selectOption('tips')
  await expect(page.getByRole('spinbutton', { name: 'Tore Arsenal', exact: true })).toBeVisible()
  const assistant = page.getByRole('region', {name:'Spieltag-Assistent'})
  await page.getByRole('tab', { name: 'Tipp-Assistent', exact: true }).click()
  await assistant.getByLabel('Tipp für Arsenal gegen Chelsea', { exact: true }).fill('0:0')
  await assistant.getByRole('button', { name: /Tipp.*speichern/ }).click()
  await enterEditorKey(page, api.validEditorKey)
  await expect(assistant.getByRole('status')).toContainText('1 gespeichert')
  await page.getByRole('link', { name: 'Gemeinsame Tipps', exact: true }).filter({ visible: true }).click()
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
  await expect(saved.getByText(/Punkte/)).toHaveCount(0)
  await page.getByRole('tab', { name: 'Punkte & Verlauf', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Abgeschlossene Spiele', exact: true })).toBeVisible()
})


test('a failed archive refresh retains a weekly draft and prevents blind saving', async ({ page, api }) => {
  await page.goto('/#/')
  await chooseCompetition(page, 'epl2026')
  await page.getByRole('tab', { name: 'Tipp-Assistent', exact: true }).click()
  const draft = page.getByLabel('Tipp für Arsenal gegen Chelsea', { exact: true })
  await draft.fill('0:0')
  api.failArchive = true
  const mobile = (page.viewportSize()?.width ?? 1440) < 1024
  if (mobile) await page.getByRole('button', { name: 'Mehr', exact: true }).click()
  else await page.getByRole('button', { name: 'Einstellungen', exact: true }).click()
  await page.getByRole('button', { name: 'Gespeicherte Daten neu laden', exact: true }).filter({ visible: true }).click()
  await page.getByRole('button', { name: 'Menü schliessen' }).click()
  await expect(page.getByText('Gespeicherte Tipps konnten nicht geladen werden. Speichern ist pausiert, damit vorhandene Tipps nicht überschrieben werden.', { exact: true })).toBeVisible({ timeout: 15000 })
  await expect(page.getByRole('button', { name: /Tipp.*speichern/ })).toBeDisabled()
  await expect(draft).toHaveValue('0:0')
  expect(api.saves).toHaveLength(0)
})


test('upcoming tips are editable immediately and closed games stay out of their way', async ({ page, api }) => {
  api.matches.ucl2026.push(fixture('closed-today', 'Closed Home', 'Closed Away', -60 * 60_000))
  await page.goto('/#/')
  await page.getByRole('tab', { name: 'Tipp-Assistent', exact: true }).click()
  await expect(page.getByLabel('Tipp für Bayern Munich gegen Arsenal', { exact: true })).toBeEditable()
  await page.getByLabel('Tipp für Bayern Munich gegen Arsenal', { exact: true }).fill('0:0')
  await expect(page.getByLabel('Tipp für Bayern Munich gegen Arsenal', { exact: true })).toHaveValue('0:0')
  await expect(page.getByRole('textbox', { name: /Tipp für Closed Home gegen Closed Away/ })).not.toBeVisible()
  await page.locator('summary').filter({ hasText: 'Bereits geschlossen' }).click()
  await expect(page.getByRole('textbox', { name: /Tipp für Closed Home gegen Closed Away/ })).toBeVisible()
  await expect(page.getByRole('textbox', { name: /Tipp für Closed Home gegen Closed Away/ })).not.toBeEditable()
  await page.goto('/#/performance')
  await expect(page.getByRole('heading', {name:'Spieltag-Assistent',exact:true})).toHaveCount(0)
  await page.getByRole('tab', { name: 'Punkte & Verlauf', exact: true }).click()
  await expect(page.getByRole('heading', {name:'Gesamter gespeicherter Punkteverlauf',exact:true})).toBeVisible()
})

test('a newly finished result updates saved tips and points without a page reload', async ({ page, api }) => {
  await page.clock.install({ time: NOW })
  api.matches.epl2026[0] = fixture('pl-next', 'Arsenal', 'Chelsea', -3 * 60 * 60_000)
  const entry = api.archive.epl2026['pl-next']
  entry.metadata.commence_time = api.matches.epl2026[0].raw_match?.commence_time
  entry.prediction.user_tip = '2:0'
  await page.goto('/#/performance')
  await chooseCompetition(page, 'epl2026')
  const pending = page.getByRole('region', { name: 'Gespeicherte Tipps' })
  await expect(pending.getByText('Ergebnis ausstehend', { exact: true })).toBeVisible()
  api.matches.epl2026[0].completed = true
  api.matches.epl2026[0].actual_score = '2:0'
  entry.post_match_result = { status: 'completed', actual_score: '2:0', points_earned: 10, algo_points: 6 }
  await page.clock.fastForward(61_000)
  await expect(pending.getByText('Ergebnis ausstehend', { exact: true })).toHaveCount(0)
  await page.getByRole('tab', { name: 'Punkte & Verlauf', exact: true }).click()
  await expect(page.getByText('Gesamtpunkte aus allen gespeicherten gemeinsamen Tipps:')).toContainText('20')
  expect(api.saves).toHaveLength(0)
})


test('a completed match accepts a marked historical tip and keeps the stored model unchanged', async ({page,api}) => {
  const entry = api.archive.ucl2026['ucl2026-result-1']
  entry.prediction.user_tip = null
  entry.prediction.top_tip = '3:0'
  await page.goto('/#/performance?view=points')
  const card = page.locator('article').filter({has:page.getByRole('textbox',{name:'Dein Tipp für Bayern Munich gegen Arsenal',exact:true})}).first()
  await expect(card.getByText('3:0',{exact:true})).toBeVisible()
  await card.getByRole('textbox').fill('2:1')
  await card.getByRole('button',{name:'Speichern',exact:true}).click()
  await enterEditorKey(page, api.validEditorKey)
  await expect(card.getByRole('status')).toContainText('10 Punkte')
  await expect(card.getByText('Dein Tipp · nachgetragen',{exact:true})).toBeVisible()
  await page.reload()
  await expect(card.getByRole('textbox')).toHaveValue('2:1')
  await expect(card.getByText('3:0',{exact:true})).toBeVisible()
  expect(entry.prediction.top_tip).toBe('3:0')
})
