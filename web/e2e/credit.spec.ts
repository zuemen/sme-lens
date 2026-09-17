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

test('集團歸戶頁可用真實統一編號查公開登記資料', async ({ page }) => {
  await page.goto('/group')

  // 預設就是決賽即席重現的案例，presenter 不必現場打字。
  const input = page.getByLabel(/統一編號/)
  await expect(input).toHaveValue('35866232')

  await page.getByTestId('gcis-submit').click()

  // 這條路徑刻意沒有離線快照可退：查到的必須是真的從公開登記資料展開的結果，
  // 所以這支測試同時也是「後端與隨附精簡索引都真的在」的驗證。
  // 逾時給到 60 秒：這條路徑的第一次請求要把隨附的 14MB gz 解壓成 47MB 的
  // SQLite（見 smelens.data.gcis.demo_index_path），在多個 worker 同時跑時
  // 觀察到偶發超過 30 秒。不是效能問題，是一次性的冷啟動成本。
  await expect(page.getByTestId('gcis-company')).toHaveText('一詮精密工業股份有限公司', {
    timeout: 60_000,
  })
  await expect(page.getByTestId('gcis-group-size')).toHaveText('4')

  const members = page.getByTestId('gcis-members')
  for (const name of [
    '一詮精密工業股份有限公司',
    '世銓科技股份有限公司',
    '惠智先進股份有限公司',
    '立誠光電股份有限公司',
  ]) {
    await expect(members).toContainText(name)
  }

  // A 層證據要點名母公司——「說出它們的老闆是誰」正是這一步的賣點。
  await expect(page.getByRole('table', { name: /法人董事證據/ })).toContainText(
    '一詮精密工業股份有限公司',
  )
})

test('貸後早期預警 Demo 全流程', async ({ page }) => {
  await page.goto('/earlywarn')

  await expect(page.getByRole('heading', { name: '貸後早期預警' })).toBeVisible()

  await page.getByTestId('earlywarn-submit').click()

  // 名單筆數與受影響曝險是這一頁要交付的兩個頭條數字
  await expect(page.getByTestId('warn-count')).toHaveText('6', { timeout: 30_000 })
  await expect(page.getByTestId('warn-exposure')).toHaveText('96,000,000')

  // 每一筆都要看得到證據路徑，不只是分數
  const table = page.getByTestId('warn-table')
  await expect(table).toContainText('宏益企業 → 泰昇精密')
  await expect(table).toContainText('宏益企業 → 昇泰貿易 → 泰昇投資')

  // 對照組（結構乾淨、三跳之外）不得被誤殺
  await expect(table).not.toContainText('禾昌五金')
})

test('可驗證憑證 Demo：憑證讓歸戶從兩戶併成一戶', async ({ page }) => {
  await page.goto('/trust')

  await expect(page.getByRole('heading', { name: /可驗證憑證/ })).toBeVisible()
  await page.getByTestId('trust-submit').click()

  // 這一頁的頭條：憑證把「姓名相同但無法確認」變成「身分經憑證確認」
  await expect(page.getByTestId('trust-groups-after')).toHaveText('1', { timeout: 60_000 })
  await expect(page.getByTestId('trust-promoted')).toHaveText('2')

  // 升級紀錄要附完整授權鏈（法人 → QVI → GLEIF 根）
  await expect(page.getByTestId('trust-table')).toContainText('一詮精密工業股份有限公司')

  // 刻意無效的那份憑證必須被擋下，而且說得出原因
  await expect(page.getByTestId('trust-rejected')).toContainText('無法回溯到信任根')

  // 尚未錨定上鏈就要照實說，不得講成已上鏈
  await expect(page.getByTestId('trust-anchored')).toContainText('尚未錨定')
})
