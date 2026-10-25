import { test, expect } from './fixtures'

test('competition buttons are keyboard accessible and switch fixture data without changing appearance', async ({ page, api }) => {
  await page.goto('/#/')
  const header = page.getByRole('banner')
  const switcher = header.getByRole('group', { name: 'Wettbewerb', exact: true })
  const switcherBounds = await switcher.boundingBox()
  if (!switcherBounds) throw new Error('Competition switcher is not visible')
  expect(switcherBounds.x).toBeGreaterThanOrEqual(0)
  expect(switcherBounds.x + switcherBounds.width).toBeLessThanOrEqual(page.viewportSize()?.width ?? 1440)
  for (const name of ['WM', 'UCL', 'PL']) {
    const bounds = await header.getByRole('button', { name, exact: true }).boundingBox()
    expect(bounds?.width).toBeGreaterThanOrEqual(44)
    expect(bounds?.height).toBeGreaterThanOrEqual(44)
  }
  await expect(header.getByRole('button', { name: 'UCL', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(header.getByRole('button', { name: 'WM', exact: true })).toHaveAccessibleDescription('Weltmeisterschaft 2026')
  await expect(header.getByRole('button', { name: 'UCL', exact: true })).toHaveAccessibleDescription('UEFA Champions League 2026/27')

  await page.keyboard.press('Tab')
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: 'WM', exact: true })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: 'UCL', exact: true })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: 'PL', exact: true })).toBeFocused()
  await page.keyboard.press('Enter')

  await expect(page.getByRole('button', { name: 'PL', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.locator('html')).toHaveAttribute('data-competition', 'epl2026')
  await expect(page.getByText('Chelsea', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('Bayern Munich', { exact: true })).toHaveCount(0)
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')

  await header.getByRole('button', { name: 'WM', exact: true }).click()
  await expect(page.locator('html')).toHaveAttribute('data-competition', 'wc2026')
  await expect(page.getByText('England', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('Chelsea', { exact: true })).toHaveCount(0)
  await header.getByRole('button', { name: 'UCL', exact: true }).click()
  await expect(page.locator('html')).toHaveAttribute('data-competition', 'ucl2026')
  await expect(page.getByText('Bayern Munich', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('England', { exact: true })).toHaveCount(0)

  expect(api.matchRequests.map(({ competition }) => competition)).toContain('epl2026')
  expect(api.forcedMatchRequests).toEqual([])
})

test('appearance can be changed independently and both preferences survive reload', async ({ page, api: _api }) => {
  await page.goto('/#/')
  const isMobile = (page.viewportSize()?.width ?? 1440) < 1024
  await page.getByRole('button', { name: isMobile ? 'Mehr' : 'Einstellungen', exact: true }).click()
  const settings = page.getByRole('dialog')
  await settings.getByRole('button', { name: /Darstellung/ }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await expect(page.getByRole('banner').getByRole('button', { name: 'UCL', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await page.keyboard.press('Escape')

  await page.getByRole('button', { name: 'PL', exact: true }).click()
  await page.reload()

  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await expect(page.locator('html')).toHaveAttribute('data-competition', 'epl2026')
  await expect(page.getByRole('button', { name: 'PL', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByText('Chelsea', { exact: true }).first()).toBeVisible()
})

test('appearance controls do not trigger a manual provider refresh', async ({ page, api }) => {
  await page.goto('/#/')
  await page.getByRole('button', { name: 'PL', exact: true }).click()
  const isMobile = (page.viewportSize()?.width ?? 1440) < 1024
  await page.getByRole('button', { name: isMobile ? 'Mehr' : 'Einstellungen', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: /Darstellung/ }).click()
  expect(api.forcedMatchRequests).toEqual([])
})
