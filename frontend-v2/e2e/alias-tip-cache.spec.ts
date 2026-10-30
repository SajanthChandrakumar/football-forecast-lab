import { test, expect, enterEditorKey } from './fixtures'
import type { ArchiveEntry } from '../src/lib/types'

test('accepted archive aliases seed canonical detail and overview tip caches', async ({ page, api }) => {
  await page.addInitScript(() => localStorage.setItem('competition', 'epl2026'))

  let postAccepted = false
  let releaseReads!: () => void
  const readGate = new Promise<void>(resolve => { releaseReads = resolve })
  let blockedArchiveReads = 0
  let blockedCoreReads = 0
  let blockedOverviewReads = 0

  await page.route(url => new URL(url).pathname === '/api/archive', async route => {
    if (postAccepted) {
      blockedArchiveReads += 1
      await readGate
    }
    return route.fulfill({ json: {} })
  })

  try {
    await page.goto('/#/')
    await expect(page.getByRole('link', { name: 'Tipp ansehen: Arsenal gegen Chelsea', exact: true })).toBeVisible()
    await page.goto('/#/match/pl-next')
    await expect(page.getByRole('spinbutton', { name: 'Tore Arsenal', exact: true })).toBeVisible()

    await page.route(url => new URL(url).pathname === '/api/matches/pl-next', async route => {
      if (postAccepted) {
        blockedCoreReads += 1
        await readGate
      }
      return route.fulfill({ json: { ...api.matches.epl2026[0], view_version: api.viewVersion, detail_level: 'core' } })
    })
    await page.route(url => {
      const parsed = new URL(url)
      return parsed.pathname === '/api/matches' && parsed.searchParams.get('overview') === 'true'
    }, async route => {
      if (postAccepted) {
        blockedOverviewReads += 1
        await readGate
      }
      return route.fulfill({ json: api.matches.epl2026.map(match => ({ ...match, detail_level: 'overview' })) })
    })
    await page.route(url => new URL(url).pathname === '/api/archive/user_tip', async route => {
      const payload = route.request().postDataJSON() as { match_id: string; user_tip: string }
      const match = api.matches.epl2026.find(item => item.id === payload.match_id)!
      const entry: ArchiveEntry = {
        metadata: {
          home_team: match.home_team,
          away_team: match.away_team,
          home_disp: match.home_disp,
          away_disp: match.away_disp,
          is_ko_phase: false,
          commence_time: match.raw_match?.commence_time as string,
        },
        prediction: { top_tip: null, max_xp: null, user_tip: payload.user_tip },
        post_match_result: { status: 'pending' },
      }
      postAccepted = true
      return route.fulfill({ json: {
        ok: true,
        points_earned: null,
        match_id: 'archive-pl-next-alias',
        canonical_match_id: 'pl-next',
        archive_entry: entry,
      } })
    })

    await page.getByRole('spinbutton', { name: 'Tore Arsenal', exact: true }).fill('3')
    await page.getByRole('spinbutton', { name: 'Tore Chelsea', exact: true }).fill('1')
    await page.getByRole('button', { name: 'Gemeinsamen Spieltipp speichern', exact: true }).click()
    await enterEditorKey(page, api.validEditorKey)
    await expect(page.getByRole('status').filter({ hasText: '3:1 gespeichert' })).toBeVisible()
    await expect.poll(() => blockedArchiveReads + blockedCoreReads).toBeGreaterThan(0)

    await page.goto('/#/')
    await expect.poll(() => blockedOverviewReads).toBeGreaterThan(0)
    await page.getByRole('combobox', { name: 'Spiele filtern', exact: true }).selectOption('upcoming')
    const row = page.locator('article.match-card').filter({ has: page.getByRole('link', { name: 'Tipp ansehen: Arsenal gegen Chelsea', exact: true }) }).first()
    await expect(row).toContainText('Gemeinsamer Tipp: 3:1')

    await page.goto('/#/match/pl-next')
    await expect(page.getByRole('spinbutton', { name: 'Tore Arsenal', exact: true })).toHaveValue('3')
    await expect(page.getByRole('spinbutton', { name: 'Tore Chelsea', exact: true })).toHaveValue('1')
  } finally {
    releaseReads()
  }
})
