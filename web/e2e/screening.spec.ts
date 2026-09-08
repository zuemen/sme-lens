import { expect, test } from '@playwright/test'

test('出金審查 Demo 全流程', async ({ page }) => {
  await page.goto('/screening')

  await expect(page.getByRole('heading', { name: '出金審查' })).toBeVisible()

  await page.getByRole('button', { name: '執行出金審查' }).click()

  // 決策卡：綜合風險 0.73 → 暫緩出金
  // exact: true — narrative_zh 與 STR 草稿內文也會提到同一組數字/決策文字，
  // 用 exact 鎖定決策卡本身的欄位，避免 strict-mode 因子字串命中多處而報錯。
  await expect(page.getByText('0.73', { exact: true })).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText('暫緩出金並啟動人工審查', { exact: true })).toBeVisible()

  // 論點：自身只有 0.33，風險來自關聯的 0.60
  await expect(page.getByText('0.33', { exact: true })).toBeVisible()
  await expect(page.getByText('0.60', { exact: true })).toBeVisible()

  // 圖譜有渲染出來
  await expect(page.getByTestId('graph-view')).toBeVisible()

  // STR 草稿可下載
  await expect(page.getByRole('button', { name: '下載草稿（.txt）' })).toBeVisible()
})

test('對照組不被誤殺', async ({ page }) => {
  await page.goto('/screening')
  await page.getByRole('combobox').selectOption('TNormalUser01')
  await page.getByRole('button', { name: '執行出金審查' }).click()
  // exact: true — narrative_zh 也會複述「予以放行」，鎖定決策卡欄位本身
  await expect(page.getByText('予以放行', { exact: true })).toBeVisible({ timeout: 30_000 })
})

test('四個頁面都走得到', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /鏈鏡/ })).toBeVisible()
  for (const name of ['出金審查', '金流圖譜', '研究成果']) {
    // exact: true — 首頁的 CTA 連結「執行出金審查 Demo」也包含「出金審查」子字串，
    // 用 exact 鎖定導覽列本身的連結，避免 strict-mode 命中多個連結。
    await page.getByRole('link', { name, exact: true }).click()
    await expect(page.locator('h1')).toBeVisible()
  }
})
