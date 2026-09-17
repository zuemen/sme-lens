// 對「線上實際跑著的那個網站」做實打驗證並存證：開啟正式網址、按下真實統編
// 查詢、把結果截圖下來。本機測試全綠不代表線上正確——前端的 VITE_API_BASE 是
// build-time 變數、後端的 includeFiles 決定隨附索引有沒有進到 function，兩者都
// 只有打線上才驗得出來（這兩個坑都實際發生過）。
//
// 用法（repo 根目錄）： node scripts/verify-live.mjs [前端網址]
import { chromium } from './../web/node_modules/playwright-core/index.mjs'
import { resolve } from 'node:path'

const base = process.argv[2] ?? 'https://sme-lens.vercel.app'
const shotDir = resolve('docs/images')

const browser = await chromium.launch()
const context = await browser.newContext({ viewport: { width: 1366, height: 1000 } })
const page = await context.newPage()

const problems = []
function check(label, ok, detail) {
  console.log(`${ok ? '✓' : '✗'} ${label}${detail ? `：${detail}` : ''}`)
  if (!ok) problems.push(label)
}

await page.goto(`${base}/group`, { waitUntil: 'networkidle' })

// 預設值就是決賽即席重現的案例，presenter 不必現場打字。
const idValue = await page.getByLabel(/統一編號/).inputValue()
check('統編輸入框預設為 35866232', idValue === '35866232', idValue)

await page.getByTestId('gcis-submit').click()
await page.getByTestId('gcis-company').waitFor({ timeout: 60_000 })

const company = (await page.getByTestId('gcis-company').textContent())?.trim()
check('查得一詮精密工業', company === '一詮精密工業股份有限公司', company)

const size = (await page.getByTestId('gcis-group-size').textContent())?.trim()
check('歸戶集團 4 家', size === '4', size)

const members = (await page.getByTestId('gcis-members').textContent()) ?? ''
for (const name of ['一詮精密工業', '世銓科技', '惠智先進', '立誠光電']) {
  check(`成員清單含 ${name}`, members.includes(name))
}

// 這條路徑刻意沒有離線快照可退，所以畫面上不該出現任何錯誤框。
const alerts = await page.getByRole('alert').count()
check('沒有錯誤框', alerts === 0, `${alerts} 個`)

await page.getByTestId('gcis-scope').scrollIntoViewIfNeeded()
await page.screenshot({ path: resolve(shotDir, 'live-gcis-group.png'), fullPage: false })
console.log(`截圖：${resolve(shotDir, 'live-gcis-group.png')}`)

await browser.close()

if (problems.length > 0) {
  console.error(`線上驗證失敗 ${problems.length} 項：${problems.join('、')}`)
  process.exitCode = 1
} else {
  console.log('線上驗證全部通過')
}
