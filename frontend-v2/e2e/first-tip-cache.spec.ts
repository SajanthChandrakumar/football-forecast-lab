import { test, expect, fixture } from './fixtures'
import type { ArchiveEntry } from '../src/lib/types'

test('first saved club tip seeds cached archive views while archive refresh is blocked', async ({ page, api }) => {
  await page.addInitScript(() => localStorage.setItem('competition', 'epl2026'))

  const other = fixture('pl-other', 'Liverpool', 'Everton')
  api.matches.epl2026.push(other)
  delete api.archive.epl2026['pl-next']
  api.archive.epl2026[other.id] = { metadata: { home_team: other.home_team, away_team: other.away_team, home_disp: other.home_team, away_disp: other.away_team, is_ko_phase: false, commence_time: other.raw_match!.commence_time! }, prediction: { top_tip: '1:0', max_xp: 2, user_tip: '2:2' }, post_match_result: { status: 'pending' } }
  const initialArchive = structuredClone(api.archive.epl2026)
  let releaseInitialFullArchive!: () => void
  const initialFullArchiveGate = new Promise<void>(resolve => { releaseInitialFullArchive = resolve })
  let failArchiveReads = false
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
    if (!postAccepted && !matchId) {
      await initialFullArchiveGate
      return route.fulfill({ json: initialArchive })
    }
    if (postAccepted) {
      blockedArchiveReads += 1
      await archiveReadGate
      if (failArchiveReads) return route.fulfill({ status: 503, json: { detail: 'Archive unavailable' } })
    }
    return route.fulfill({ json: matchId ? (api.archive.epl2026[matchId] ? { [matchId]: api.archive.epl2026[matchId] } : {}) : api.archive.epl2026 })
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
    api.archive.epl2026[payload.match_id] = entry
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
    await page.getByRole('button', { name: 'Meinen Spieltipp speichern', exact: true }).click()
    await expect(page.getByRole('status').filter({ hasText: '3:1 gespeichert' })).toBeVisible()
    await expect.poll(() => blockedArchiveReads).toBeGreaterThan(0)
    expect(acceptedTip).toBe('3:1')
    releaseInitialFullArchive()

    await page.goto('/#/')
    await expect.poll(() => blockedArchiveReads).toBeGreaterThan(1)
    await expect(page.getByText('Meine gespeicherten Tipps werden geladen.', { exact: true })).toBeVisible()
    await expect(page.getByRole('spinbutton', { name: 'Tore Liverpool', exact: true })).toHaveCount(0)
    await page.getByRole('combobox', { name: 'Spiele filtern', exact: true }).selectOption('upcoming')
    const row = page.locator('article.match-card').filter({ has: page.getByRole('link', { name: 'Tipp ansehen: Arsenal gegen Chelsea', exact: true }) }).first()
    await expect(row).toContainText('Mein Tipp: 3:1')
    failArchiveReads = true
    releaseArchiveReads()
    await page.goto('/#/performance')
    await expect(page.getByText('Auswertung nicht verfügbar', { exact: true })).toBeVisible()
    await page.getByRole('tab', { name: 'Punkte & Verlauf', exact: true }).click()
    await expect(page.getByText('Auswertung nicht verfügbar', { exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Übersicht', exact: true })).toHaveCount(0)
    await page.getByRole('tab', { name: 'Modellvergleich', exact: true }).click()
    await expect(page.getByText('Auswertung nicht verfügbar', { exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Gesamte gespeicherte Modellhistorie', exact: true })).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Wahrscheinlichkeitsgüte', exact: true })).toBeVisible()
  } finally {
    releaseInitialFullArchive()
    releaseArchiveReads()
  }
})
