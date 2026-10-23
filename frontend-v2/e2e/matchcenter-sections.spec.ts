import { chooseCompetition, expect, test } from './fixtures'

test('archive failure stays distinct from an empty tip list while evaluation remains reachable', async ({ page, api }) => {
  api.failArchive = true
  await page.goto('/#/performance')
  await expect(page.getByRole('heading', { name: 'Auswertung nicht verfügbar', exact: true })).toBeVisible()
  await expect(page.getByText(/Noch keine gespeicherten Tipps für anstehende Spiele/)).toHaveCount(0)
  await page.getByRole('tab', { name: 'Modellvergleich', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Wahrscheinlichkeitsgüte', exact: true })).toBeVisible()
})

test('an unavailable world cup simulation does not render an empty title ranking as results', async ({ page, api: _api }) => {
  await page.goto('/#/simulator')
  await chooseCompetition(page, 'wc2026')
  await expect(page.getByRole('heading', { name: 'Keine Simulation verfügbar', exact: true })).toBeVisible()
  await expect(page.getByRole('list', { name: 'Titelchancen nach Wahrscheinlichkeit' })).toHaveCount(0)
})

test('performance tabs expose accessible panels and retain history filters', async ({ page, api: _api }) => {
  await page.goto('/#/performance')

  const savedTipsTab = page.getByRole('tab', { name: 'Gespeicherte Tipps' })
  const pointsTab = page.getByRole('tab', { name: 'Punkte & Verlauf' })
  await expect(page.getByRole('tablist')).toHaveAttribute('aria-label', /.+/)
  await expect(savedTipsTab).toHaveAttribute('aria-selected', 'true')
  await expect(savedTipsTab).toHaveAttribute('aria-controls', /.+/)

  await savedTipsTab.focus()
  await page.keyboard.press('ArrowRight')
  await expect(pointsTab).toHaveAttribute('aria-selected', 'true')
  await expect(page).toHaveURL(/view=points/)

  const panel = page.getByRole('tabpanel')
  const pointsTabId = await pointsTab.getAttribute('id')
  expect(pointsTabId).not.toBeNull()
  await expect(panel).toHaveAttribute('aria-labelledby', pointsTabId!)
  await expect(page.getByText('Abgeschlossene Spiele', { exact: true }).first()).toBeVisible()

  const historyFilter = page.getByRole('button', { name: 'Falsche Tendenz', exact: true })
  await historyFilter.click()
  await expect(historyFilter).toHaveAttribute('aria-pressed', 'true')
  await pointsTab.focus()
  await page.keyboard.press('ArrowLeft')
  await expect(savedTipsTab).toHaveAttribute('aria-selected', 'true')
  await savedTipsTab.focus()
  await page.keyboard.press('ArrowRight')
  await expect(historyFilter).toHaveAttribute('aria-pressed', 'true')

})

test('simulator switches between sorted title chances and the complete knockout view', async ({ page, api }) => {
  await page.goto('/#/')
  await chooseCompetition(page, 'wc2026')
  await page.route('**/api/simulate_knockout**', (route) => route.fulfill({
    json: {
      status: 'success',
      n_runs: 500,
      round_labels: ['Achtelfinale', 'Viertelfinale', 'Halbfinale', 'Finale'],
      results: [
        { team: 'Australia', elo: 1900, reached_qf: 50, reached_sf: 30, reached_final: 20, champion: 20 },
        { team: 'Brazil', elo: 2050, reached_qf: 80, reached_sf: 65, reached_final: 45, champion: 60 },
        { team: 'Croatia', elo: 1950, reached_qf: 50, reached_sf: 25, reached_final: 10, champion: 0 },
        { team: 'Argentina', elo: 2000, reached_qf: 70, reached_sf: 45, reached_final: 30, champion: 20 },
      ],
      bracket: [{ home: 'Brazil', away: 'Argentina' }],
    },
  }))

  await page.goto('/#/simulator')
  const titlesTab = page.getByRole('tab', { name: 'Titelchancen' })
  const roundsTab = page.getByRole('tab', { name: 'Alle Runden' })
  await expect(titlesTab).toHaveAttribute('aria-selected', 'true')

  const chances = page.getByRole('list', { name: 'Titelchancen nach Wahrscheinlichkeit' }).getByRole('listitem')
  await expect(chances).toHaveCount(4)
  for (const [index, team, percent] of [
    [0, 'Brazil', '60.0%'],
    [1, 'Argentina', '20.0%'],
    [2, 'Australia', '20.0%'],
    [3, 'Croatia', '0.0%'],
  ] as const) {
    await expect(chances.nth(index)).toContainText(team)
    await expect(chances.nth(index)).toContainText(percent)
  }
  await expect(page.getByText(/500/).first()).toBeVisible()
  await expect(page.getByText(/kleine Stichprobe/i)).toBeVisible()

  await roundsTab.click()
  await expect(roundsTab).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByText(/kleine Stichprobe/i)).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'Erreicht Viertelfinale' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Startpaarungen' })).toBeVisible()
  await expect(page.getByText('Brazil', { exact: true }).last()).toBeVisible()
  await expect(page.getByText('Argentina', { exact: true }).last()).toBeVisible()
  expect(api.unexpected).toEqual([])
})
