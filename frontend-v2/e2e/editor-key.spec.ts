import { test, expect, chooseCompetition } from './fixtures'

const competitions = [
  { id: 'wc2026', label: 'WM', matchId: 'wc-next', home: 'England', away: 'Switzerland' },
  { id: 'ucl2026', label: 'UCL', matchId: 'ucl-next', home: 'Bayern Munich', away: 'Arsenal' },
  { id: 'epl2026', label: 'PL', matchId: 'pl-next', home: 'Arsenal', away: 'Chelsea' },
] as const

for (const competition of competitions) {
  test(`${competition.label} shared tips save without an editor key`, async ({ page, api }) => {
    const nativePrompts: string[] = []
    page.on('dialog', async dialog => {
      nativePrompts.push(dialog.message())
      await dialog.dismiss()
    })

    await page.goto('/#/')
    await chooseCompetition(page, competition.id)
    await page.goto(`/#/match/${competition.matchId}`)
    await page.getByLabel(`Tore ${competition.home}`).fill('1')
    await page.getByLabel(`Tore ${competition.away}`).fill('0')
    await page.getByRole('button', { name: 'Gemeinsamen Spieltipp speichern', exact: true }).click()

    await expect(page.getByRole('status')).toContainText('1:0 gespeichert')
    await expect(page.getByRole('dialog', { name: 'Editor-Schlüssel' })).toHaveCount(0)
    expect(nativePrompts).toEqual([])
    expect(api.saves).toEqual([{ match_id: competition.matchId, user_tip: '1:0', competition: competition.id }])
    expect(api.sharedWriteAuthorizations).toEqual([undefined])
  })
}
