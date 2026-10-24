import { test, expect } from './fixtures'

test('shared writes use a masked transient key and ask again after an invalid key', async ({ page, api }) => {
  api.requireEditorKey = true
  await page.goto('/#/match/ucl-next')
  await page.getByLabel('Tore Bayern Munich').fill('1')
  await page.getByLabel('Tore Arsenal').fill('0')
  await page.getByRole('button', { name: 'Gemeinsamen Spieltipp speichern' }).click()

  const dialog = page.getByRole('dialog', { name: 'Editor-Schlüssel' })
  await expect(dialog).toBeVisible()
  const password = dialog.getByLabel('Schlüssel zum Speichern gemeinsamer Änderungen eingeben.')
  await expect(password).toHaveAttribute('type', 'password')
  await password.fill('wrong-key')
  await dialog.getByRole('button', { name: 'Weiter' }).click()
  await expect(page.getByRole('alert')).toContainText('Editor-Schlüssel ungültig')
  await expect(dialog).toHaveCount(0)

  await page.getByRole('button', { name: 'Gemeinsamen Spieltipp speichern' }).click()
  await expect(dialog).toBeVisible()
  await dialog.getByLabel('Schlüssel zum Speichern gemeinsamer Änderungen eingeben.').fill(api.validEditorKey)
  await dialog.getByRole('button', { name: 'Weiter' }).click()
  await expect(page.getByRole('status')).toContainText('Gemeinsamer Spieltipp 1:0 gespeichert.')
  expect(api.editorKeyAttempts).toEqual(['wrong-key', api.validEditorKey])
  const storedValues = await page.evaluate(() => {
    const values = (storage: Storage) => Array.from({ length: storage.length }, (_, index) => {
      const key = storage.key(index)
      return key ? `${key}=${storage.getItem(key) ?? ''}` : ''
    })
    return [...values(localStorage), ...values(sessionStorage)].join('\n')
  })
  expect(storedValues).not.toContain(api.validEditorKey)
  expect(storedValues).not.toContain('wrong-key')
})
