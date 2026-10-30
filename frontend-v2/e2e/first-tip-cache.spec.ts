import { test, expect, enterEditorKey } from './fixtures'
import type { ArchiveEntry } from '../src/lib/types'

test('first saved club tip seeds cached archive views while archive refresh is blocked', async ({ page, api }) => {
  await page.addInitScript(() => localStorage.setItem('competition', 'epl2026'))

  let postAccepted = false
  let releaseArchiveReads!: () => void
  const archiveReadGate = new Promise<void>(resolve => { releaseArchiveReads = resolve })
  const archiveReads: (string | null)[] = []
  let blockedArchiveReads = 0
  let acceptedTip = ''

  await page.route(url => new URL(url).pathname === '/api/archive', async route => {
    const url = new URL(route.request().url())
    const matchId = url.searchParams.get('match_id')
    archiveReads.push(matchId)
    if (postAccepted) {
      blockedArchiveReads += 1
      await archiveReadGate
    }
    return route.fulfill({ json: {} })
  })
  await page.route(url => new URL(url).pathname === '/api/archive/user_tip', async route => {
    const payload = route.request().postDataJSON() as { match_id: string; user_tip: string }
    acceptedTip = payload.user_tip
    postAccepted = true
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
    return route.fulfill({ json: { ok: true, points_earned: null, match_id: payload.match_id, archive_entry: entry } })
  })

  try {
    await page.goto('/#/')
    await page.getByRole('combobox', { name: 'Spiele filtern', exact: true }).selectOption('tips')
    await expect.poll(() => archiveReads).toContain(null)

    await page.goto('/#/match/pl-next')
    await expect(page.getByRole('spinbutton', { name: 'Tore Arsenal', exact: true })).toBeVisible()
    await expect.poll(() => archiveReads).toContain('pl-next')

    await page.getByRole('spinbutton', { name: 'Tore Arsenal', exact: true }).fill('3')
    await page.getByRole('spinbutton', { name: 'Tore Chelsea', exact: true }).fill('1')
    await page.getByRole('button', { name: 'Gemeinsamen Spieltipp speichern', exact: true }).click()
    await enterEditorKey(page, api.validEditorKey)
    await expect(page.getByRole('status').filter({ hasText: '3:1 gespeichert' })).toBeVisible()
    await expect.poll(() => blockedArchiveReads).toBeGreaterThan(0)
    expect(acceptedTip).toBe('3:1')

    await page.goto('/#/')
    await expect.poll(() => blockedArchiveReads).toBeGreaterThan(1)
    await page.getByRole('combobox', { name: 'Spiele filtern', exact: true }).selectOption('upcoming')
    const row = page.locator('article.match-card').filter({ has: page.getByRole('link', { name: 'Tipp ansehen: Arsenal gegen Chelsea', exact: true }) }).first()
    await expect(row).toContainText('Gemeinsamer Tipp: 3:1')
  } finally {
    releaseArchiveReads()
  }
})
