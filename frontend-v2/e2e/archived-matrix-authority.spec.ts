import { test, expect, NOW } from './fixtures'

test('completed club model details use the bounded frozen matrix over compact core and current analysis', async ({ page, api }) => {
  const match = api.matches.ucl2026[0]
  match.completed = true
  match.actual_score = '1:0'

  const archived = api.archive.ucl2026[match.id]
  archived.post_match_result = { status: 'completed', actual_score: '1:0' }
  archived.prediction = {
    ...archived.prediction,
    model_tip: '1:0',
    top_tip: '1:0',
    frozen_at: new Date(NOW.getTime() - 2 * 86_400_000).toISOString(),
    probabilities: { home: .52, draw: .28, away: .20 },
    matrix: { 1: { 0: .73 }, 0: { 0: .27 } },
    xp_tips: [{ Tipp: '1:0', xP: 4.1 }],
  }
  api.prediction = {
    model_tip: '5:0',
    top_tip: '5:0',
    probabilities: { home: .9, draw: .06, away: .04 },
    matrix: { 5: { 0: .88 }, 1: { 1: .12 } },
    xp_tips: [{ Tipp: '5:0', xP: 9.9 }],
    source: 'current-analysis-fixture',
    observed_at: NOW.toISOString(),
  }
  api.viewVersion = 'frozen-matrix-view-v1'

  const compactCore = {
    ...match,
    detail_level: 'core' as const,
    view_version: api.viewVersion,
    archived_prediction: {
      model_tip: '1:0',
      top_tip: '1:0',
      max_xp: archived.prediction.max_xp,
      frozen_at: archived.prediction.frozen_at,
      probabilities: archived.prediction.probabilities,
      source: 'frozen-model',
      observed_at: archived.prediction.observed_at,
    },
  }
  delete compactCore.matrix
  delete compactCore.regulation_matrix
  delete compactCore.xp_tips
  delete compactCore.home_form
  delete compactCore.away_form
  delete compactCore.match_intelligence

  await page.route(url => new URL(url).pathname === `/api/matches/${match.id}`, route => route.fulfill({ json: compactCore }))
  await page.goto(`/#/match/${match.id}?view=model`)

  await expect(page.getByRole('heading', { name: 'Ergebnis-Alternativen', exact: true })).toBeVisible()
  await expect(page.getByText('73.0 % Chance', { exact: true })).toBeVisible()
  await expect(page.getByText('88.0 % Chance', { exact: true })).toHaveCount(0)
  await expect(page.getByText('5:0', { exact: true })).toHaveCount(0)
  await expect(page.getByText('1:0', { exact: true }).first()).toBeVisible()
})
