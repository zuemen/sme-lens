import { expect, test } from '@playwright/test'

test('授信意見書 Demo 全流程', async ({ page }) => {
  await page.goto('/credit')

  await expect(page.getByRole('heading', { name: '授信意見書' })).toBeVisible()

  await page.getByRole('button', { name: '產生授信意見書' }).click()

  await expect(page.getByRole('heading', { name: '授信關注等級' })).toBeVisible({
    timeout: 30_000,
  })
  await expect(page.getByRole('heading', { name: '建議', exact: true })).toBeVisible()
})

test('集團歸戶 Demo 全流程', async ({ page }) => {
  await page.goto('/group')

  await expect(page.getByRole('heading', { name: '集團歸戶' })).toBeVisible()

  await page.getByRole('button', { name: '執行集團歸戶' }).click()

  await expect(
    page.getByRole('heading', {
      name: '隱性關聯（客戶未申報，關係圖比對出來的共同持有／共用董監事）',
    }),
  ).toBeVisible({ timeout: 30_000 })
})

test('導覽列可從授信意見書走到集團歸戶', async ({ page }) => {
  await page.goto('/credit')
  await expect(page.getByRole('heading', { name: '授信意見書' })).toBeVisible()

  await page.getByRole('link', { name: '集團歸戶', exact: true }).click()
  await expect(page.getByRole('heading', { name: '集團歸戶' })).toBeVisible()
})
