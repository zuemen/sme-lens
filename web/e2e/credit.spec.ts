import { expect, test } from '@playwright/test'

test('授信意見書 Demo 全流程', async ({ page }) => {
  await page.goto('/credit')

  await expect(page.getByRole('heading', { name: '授信意見書' })).toBeVisible()

  await page.getByRole('button', { name: '產生授信意見書' }).click()

  await expect(page.getByRole('heading', { name: '授信關注等級' })).toBeVisible({
    timeout: 30_000,
  })
  await expect(page.getByRole('heading', { name: '建議', exact: true })).toBeVisible()

  // 授信關注分數 0.82（關注）。「0.82」在節點表格的目標公司那一列也會重複出現，
  // 用 .first() 鎖定「授信關注等級」面板本身（DOM 順序在節點表格之前）。
  await expect(page.getByText('0.82', { exact: true }).first()).toBeVisible()

  // 建議文字：這是這頁真正要交付給審查人員的一句話，數字或建議算錯，這裡就會紅燈。
  await expect(
    page.getByText('建議暫緩核貸，先行實地查核關係人交易與主要買方合約之真實性。', { exact: true }),
  ).toBeVisible()
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

  // 客戶申報 2 個集團，關係圖歸戶後只剩 1 個——這是這頁要交付的頭條數字。
  await expect(page.getByTestId('group-count-declared')).toContainText('2')
  await expect(page.getByTestId('group-count-actual')).toContainText('1')

  // 曝險落差：最大申報集團 42,000,000 → 併入後實際 50,000,000，差 8,000,000。
  // 一個之前踩過的 0 元曝險落差 bug，若重現會在這裡直接紅燈。
  await expect(page.getByTestId('group-exposure-declared')).toContainText('42,000,000')
  await expect(page.getByTestId('group-exposure-actual')).toContainText('50,000,000')
  await expect(page.getByTestId('group-exposure-gap')).toContainText('8,000,000')
})

test('導覽列可從授信意見書走到集團歸戶', async ({ page }) => {
  await page.goto('/credit')
  await expect(page.getByRole('heading', { name: '授信意見書' })).toBeVisible()

  await page.getByRole('link', { name: '集團歸戶', exact: true }).click()
  await expect(page.getByRole('heading', { name: '集團歸戶' })).toBeVisible()
})
