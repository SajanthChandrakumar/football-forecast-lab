import { test, expect, NOW, chooseCompetition } from './fixtures'
import type { Page } from '@playwright/test'
import type { Match } from '../src/lib/types'

const verifiedHistory = (team: string, opponent: string, prefix: string) =>
  Array.from({ length: 12 }, (_, index) => ({
    fixture_id: `${prefix}-${index}`,
    played_at: new Date(NOW.getTime() - (index + 1) * 86_400_000).toISOString(),
    competition_name: index % 3 === 0 ? 'Premier League' : index % 3 === 1 ? 'FA Cup' : 'Champions League',
    competition_kind: index % 3 === 0 ? 'league' : index % 3 === 1 ? 'cup' : 'europe',
    identity_verified: true,
    home_id: index % 2 ? 'opponent-id' : `${prefix}-id`,
    home_team: index % 2 ? opponent : team,
    away_id: index % 2 ? `${prefix}-id` : 'opponent-id',
    away_team: index % 2 ? team : opponent,
    home_logo: index === 0 ? 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxNiAxNiI+PC9zdmc+' : null,
    away_logo: null,
    venue: index % 2 ? 'away' as const : 'home' as const,
    score: '2:1',
    goals_for: 2,
    goals_against: 1,
    result: index % 3 === 1 ? 'D' as const : 'W' as const,
    result_type: index === 0 ? 'PEN' : index === 1 ? 'AET' : 'FT',
    score_90: { home: 1, away: 1 },
    score_aet: index === 1 ? { home: 2, away: 1 } : null,
    penalties: index === 0 ? { home: 4, away: 3 } : null,
  }))

const legacyModelProbabilities = { home: 0.62, draw: 0.23, away: 0.15 }

async function expectLegacyModelHint(page: Page) {
  const modelPanel = page.getByRole('tabpanel', { name: 'Modelldaten' })
  await expect(modelPanel.getByText('Modellprognose · Quelle nicht belegt', { exact: false })).toBeVisible()
  await expect(modelPanel.getByText('62%', { exact: true })).toBeVisible()
  await expect(modelPanel.getByText('23%', { exact: true })).toBeVisible()
  await expect(modelPanel.getByText('15%', { exact: true })).toBeVisible()
}

function addVerifiedForms(match: Match) {
  match.home_team = 'Brighton & Hove Albion'
  match.away_team = 'Tottenham Hotspur'
  match.home_disp = match.home_team
  match.away_disp = match.away_team
  match.home_form = {
    scope: 'all_competitions',
    status: 'fresh',
    source: 'espn',
    on_fire: false,
    form: ['W', 'D', 'W'],
    matches: verifiedHistory(match.home_team, 'Chelsea', 'brighton') as unknown as NonNullable<Match['home_form']>['matches'],
  }
  match.away_form = {
    scope: 'all_competitions',
    status: 'fresh',
    source: 'espn',
    on_fire: false,
    form: ['W', 'D', 'W'],
    matches: verifiedHistory(match.away_team, 'Arsenal', 'tottenham') as unknown as NonNullable<Match['away_form']>['matches'],
  }
}

async function waitForLayoutFrame(page: Page) {
  await page.evaluate(() => new Promise<void>(resolve => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
  }))
}

test('detail uses model probabilities and makes no pool-context request', async ({ page, api }) => {
  api.prediction = {
    model_tip: '1:0',
    probabilities: { home: 0.62, draw: 0.23, away: 0.15 },
    source_mode: 'odds+elo',
    status: 'fresh',
    observed_at: NOW.toISOString(),
    input_provenance: {
      odds: { source: 'odds_api', status: 'fresh', observed_at: NOW.toISOString() },
      elo: { source: 'clubelo', status: 'fresh', observed_at: NOW.toISOString() },
    },
  }
  const requests: string[] = []
  page.on('request', request => requests.push(request.url()))

  await page.goto('/#/match/ucl-next')
  await page.getByRole('tab', { name: 'Modelldaten', exact: true }).click()

  const hint = page.getByText('Modellprognose · Buchmacherquoten + Elo', { exact: false })
  const modelPanel = page.getByRole('tabpanel', { name: 'Modelldaten' })
  await expect(hint).toBeVisible()
  await expect(modelPanel.getByText('62%', { exact: true })).toBeVisible()
  await expect(modelPanel.getByText('23%', { exact: true })).toBeVisible()
  await expect(modelPanel.getByText('15%', { exact: true })).toBeVisible()
  await expect(page.getByText('Pool-Tipp und Rundendaten', { exact: true })).toHaveCount(0)
  expect(requests.some(url => url.includes('/pool-context/'))).toBe(false)
})

test('legacy World Cup model probabilities remain visible without source mode', async ({ page, api }) => {
  const legacyMatch = api.matches.wc2026[0]
  legacyMatch.probabilities = legacyModelProbabilities
  legacyMatch.source_mode = undefined
  api.prediction = {
    model_tip: '1:0',
    probabilities: legacyModelProbabilities,
    source_mode: undefined,
    status: 'fresh',
    observed_at: NOW.toISOString(),
  }

  await page.goto('/')
  await chooseCompetition(page, 'wc2026')
  await page.goto('/#/match/wc-next')
  await page.getByRole('tab', { name: 'Modelldaten', exact: true }).click()

  await expectLegacyModelHint(page)
})

test('archived played model probabilities remain visible without source mode', async ({ page, api }) => {
  const playedMatch = api.matches.ucl2026[0]
  playedMatch.completed = true
  playedMatch.raw_match.commence_time = new Date(NOW.getTime() - 86_400_000).toISOString()
  Object.assign(api.archive.ucl2026[playedMatch.id].prediction, {
    model_tip: '1:0',
    probabilities: legacyModelProbabilities,
    source_mode: undefined,
    observed_at: NOW.toISOString(),
  })

  await page.goto('/#/match/ucl-next')
  await page.getByRole('tab', { name: 'Modelldaten', exact: true }).click()

  await expectLegacyModelHint(page)
})

test('ready current model probabilities replace stale pending cache state in the hint', async ({ page, api }) => {
  api.matches.ucl2026[0].calculation_status = 'pending'
  api.prediction = {
    model_tip: '1:0',
    probabilities: legacyModelProbabilities,
    source_mode: 'odds+elo',
    status: 'fresh',
    observed_at: NOW.toISOString(),
  }

  await page.goto('/#/match/ucl-next')
  await page.getByRole('tab', { name: 'Modelldaten', exact: true }).click()
  const modelPanel = page.getByRole('tabpanel', { name: 'Modelldaten' })

  await expect(modelPanel.getByText('Modellprognose · Buchmacherquoten + Elo', { exact: false })).toBeVisible()
  await expect(modelPanel.getByText('62%', { exact: true })).toBeVisible()
  await expect(modelPanel.getByText('Analyse wird vorbereitet.', { exact: true })).toHaveCount(0)
})

test('detail form, expected-goals cards, and market outcomes fit phone, tablet, and desktop widths', async ({ page, api }, testInfo) => {
  test.skip(testInfo.project.name !== 'phone-375', 'Runs one responsive sweep at the requested widths.')
  addVerifiedForms(api.matches.ucl2026[0])

  await page.goto('/#/match/ucl-next')
  await page.getByRole('tab', { name: 'Form', exact: true }).click()
  const xg = page.getByRole('group', { name: 'Erwartete Tore laut Modell' })
  const xgCards = xg.getByRole('group')
  const home = page.getByRole('region', { name: 'Brighton & Hove Albion Pflichtspielform' })
  await expect(home.getByRole('img', { name: 'Brighton & Hove Albion Wappen' }).first()).toBeVisible()
  await expect(home.getByRole('img', { name: /Wappen nicht verfügbar/ }).first()).toBeVisible()
  const homeHistory = home.locator('ol > li')
  await expect(homeHistory).toHaveCount(5)
  await expect(homeHistory.first()).toContainText('02. Okt. 2026, 14:00')
  await expect(homeHistory.first()).toContainText('2:1')
  await expect(home.getByText('Elfmeterschießen 4:3', { exact: false })).toBeVisible()
  await expect(home.getByText('Nach Verlängerung 2:1', { exact: false })).toBeVisible()
  await home.getByRole('button', { name: 'Weitere Spiele (10)' }).click()
  await expect(homeHistory).toHaveCount(10)
  const formFilters = home.getByRole('group', { name: 'Brighton & Hove Albion: Form nach Wettbewerb' })
  await formFilters.getByRole('button', { name: 'Liga', exact: true }).click()
  await expect(home.getByText('Geprüfte Pflichtspiele · Liga', { exact: false })).toBeVisible()
  await expect(homeHistory).toHaveCount(4)
  await formFilters.getByRole('button', { name: 'Pokal', exact: true }).click()
  await expect(home.getByText('Geprüfte Pflichtspiele · Pokal', { exact: false })).toBeVisible()
  await formFilters.getByRole('button', { name: 'Europa', exact: true }).click()
  await expect(home.getByText('Geprüfte Pflichtspiele · Europa', { exact: false })).toBeVisible()
  await formFilters.getByRole('button', { name: 'Alle Pflichtspiele', exact: true }).click()

  for (const width of [375, 788, 1024, 1440]) {
    await page.setViewportSize({ width, height: 980 })
    await expect(xgCards).toHaveCount(2)
    const readGeometry = async () => {
      await waitForLayoutFrame(page)
      const geometry = await xg.evaluate(element => {
        const rect = (node: Element) => {
          const { x, y, width, height } = node.getBoundingClientRect()
          return { x, y, width, height }
        }
        const cards = Array.from(element.children)
        const [homeForm, awayForm] = Array.from(document.querySelectorAll('.club-team-form-history'))
        return {
          grid: rect(element),
          cards: cards.map(rect),
          forms: [homeForm, awayForm].map(node => node ? rect(node) : null),
        }
      })
      const sectionOverflow = await home.evaluate(element => {
        const sectionRect = element.getBoundingClientRect()
        const offenders = Array.from(element.querySelectorAll('*'))
          .filter(child => child.scrollWidth > child.clientWidth + 1)
          .slice(0, 5)
          .map(child => ({
            tag: child.tagName.toLowerCase(),
            className: typeof child.className === 'string' ? child.className : '',
            text: child.textContent?.trim().slice(0, 80),
            clientWidth: child.clientWidth,
            scrollWidth: child.scrollWidth,
            rect: (() => {
              const { x, right, width } = child.getBoundingClientRect()
              return { x, right, width }
            })(),
          }))
        return {
          selector: '.club-team-form-history',
          rect: { x: sectionRect.x, right: sectionRect.right, width: sectionRect.width },
          clientWidth: element.clientWidth,
          scrollWidth: element.scrollWidth,
          offenders,
        }
      })
      return { geometry, sectionOverflow }
    }
    let previousSample = ''
    let stableSample: Awaited<ReturnType<typeof readGeometry>> | undefined
    await expect.poll(async () => {
      const sample = await readGeometry()
      const [homeCard, awayCard] = sample.geometry.cards
      const [homeForm, awayForm] = sample.geometry.forms
      const isValid = homeCard != null && awayCard != null && homeForm != null && awayForm != null
        && Math.abs(homeCard.width - awayCard.width) <= 1
        && homeCard.width + awayCard.width > sample.geometry.grid.width * 0.9
        && (Math.abs(homeForm.y - awayForm.y) < 2) === (width >= 1024)
        && sample.sectionOverflow.scrollWidth <= sample.sectionOverflow.clientWidth
      const serialized = JSON.stringify(sample)
      const isStable = serialized === previousSample
      previousSample = serialized
      if (isValid && isStable) {
        stableSample = sample
        return 'stable valid geometry'
      }
      return serialized
    }, { message: `Responsive geometry should settle at ${width}px`, timeout: 2_000 }).toBe('stable valid geometry')
    const { geometry, sectionOverflow } = stableSample!
    const [homeXgBox, awayXgBox] = geometry.cards
    const [homeBox, awayBox] = geometry.forms
    expect(homeXgBox).toBeDefined()
    expect(awayXgBox).toBeDefined()
    expect(homeBox).not.toBeNull()
    expect(awayBox).not.toBeNull()
    expect(Math.abs(homeXgBox.width - awayXgBox.width), JSON.stringify({ width, ...geometry })).toBeLessThanOrEqual(1)
    expect(homeXgBox.width + awayXgBox.width).toBeGreaterThan(geometry.grid.width * 0.9)
    expect(Math.abs(homeBox!.y - awayBox!.y) < 2).toBe(width >= 1024)
    expect(sectionOverflow.scrollWidth, JSON.stringify(sectionOverflow)).toBeLessThanOrEqual(sectionOverflow.clientWidth)
    const row = home.locator('ol > li').first().locator('.club-form-scoreline')
    const homeSide = await row.getByRole('group', { name: /Brighton & Hove Albion/ }).boundingBox()
    const awaySide = await row.getByRole('group', { name: /Chelsea/ }).boundingBox()
    const scoreBox = await row.locator('.club-form-score').boundingBox()
    const formContentWidth = await home.evaluate(element => {
      const style = getComputedStyle(element)
      return element.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)
    })
    expect(homeSide).not.toBeNull()
    expect(awaySide).not.toBeNull()
    expect(scoreBox).not.toBeNull()
    if (formContentWidth >= 416) {
      expect(homeSide!.x + homeSide!.width).toBeLessThanOrEqual(scoreBox!.x + 2)
      expect(scoreBox!.x + scoreBox!.width).toBeLessThanOrEqual(awaySide!.x + 2)
      expect(Math.abs((homeSide!.y + homeSide!.height / 2) - (awaySide!.y + awaySide!.height / 2))).toBeLessThanOrEqual(2)
    } else {
      expect(awaySide!.y).toBeGreaterThan(homeSide!.y)
      expect(Math.abs(homeSide!.x - awaySide!.x)).toBeLessThanOrEqual(2)
    }

    const stats = home.locator('dl[aria-label="Formstatistik"]')
    await expect(stats.locator(':scope > div')).toHaveCount(3)
    const statBoxes = await stats.locator(':scope > div').evaluateAll(elements => elements.map(element => {
      const { x, width } = element.getBoundingClientRect()
      return { x, width }
    }))
    expect(statBoxes.every(item => Math.abs(item.width - statBoxes[0].width) < 1)).toBe(true)
    await page.getByRole('tabpanel', { name: 'Form' }).screenshot({ path: testInfo.outputPath(`detail-form-${width}.png`) })
  }

  await page.getByRole('tab', { name: 'Markt', exact: true }).click()
  const marketOutcomes = page.getByRole('list', { name: 'Buchmacherchancen für Heimsieg, Remis und Auswärtssieg' })
  await expect(marketOutcomes.getByRole('listitem')).toHaveCount(3)
  await expect(page.getByText(/Dezimalquoten für Heimsieg, Remis und Auswärtssieg/)).toBeVisible()
  for (const width of [375, 788]) {
    await page.setViewportSize({ width, height: 980 })
    const boxes = await marketOutcomes.getByRole('listitem').evaluateAll(elements => elements.map(element => {
      const { x, y, width } = element.getBoundingClientRect()
      return { x, y, width }
    }))
    expect(Math.abs(boxes[0].y - boxes[1].y) < 2).toBe(width >= 640)
    if (width >= 640) expect(Math.abs(boxes[0].width - boxes[1].width)).toBeLessThanOrEqual(1)
    await marketOutcomes.screenshot({ path: testInfo.outputPath(`detail-market-${width}.png`) })
  }
})
