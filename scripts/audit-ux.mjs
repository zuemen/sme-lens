// 對線上網站逐頁、逐斷點做可用性與無障礙的機械檢查。
//
// 為什麼要用程式檢查而不是看截圖：觸控目標尺寸、對比值、橫向溢出、標題階層
// 這些都是可量測的數字，用眼睛看只會漏。本腳本針對的是 UI/UX 規範裡標為
// CRITICAL／HIGH 的項目（無障礙、觸控、版面響應），輸出具體到元素的清單。
//
// 用法：node scripts/audit-ux.mjs [基底網址]
import { chromium } from './../web/node_modules/playwright-core/index.mjs'

const base = process.argv[2] ?? 'https://sme-lens.vercel.app'
const ROUTES = [
  '/',
  '/credit',
  '/group',
  '/earlywarn',
  '/trust',
  '/screening',
  '/workbench',
  '/research',
]
const VIEWPORTS = [
  { name: 'mobile', width: 390, height: 844 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'desktop', width: 1366, height: 900 },
]

/** 在頁面內執行的檢查。回傳純資料，不做判斷——判斷留在 node 這一側。 */
const collect = () => {
  const out = { findings: [] }
  const add = (rule, detail) => out.findings.push({ rule, detail })

  // 1) 橫向溢出：手機上最常見也最明顯的破版
  const de = document.documentElement
  if (de.scrollWidth > de.clientWidth + 1) {
    // 找出實際超出視窗右緣的元素，否則只知道有溢出卻不知道是誰造成的
    const culprits = []
    for (const el of document.querySelectorAll('*')) {
      const r = el.getBoundingClientRect()
      if (r.width > 0 && r.right > de.clientWidth + 1 && !el.closest('[data-allow-overflow]')) {
        const scrollable = el.closest('.overflow-x-auto, .nav-scroll')
        if (!scrollable) {
          culprits.push(`${el.tagName.toLowerCase()}.${el.className}`.slice(0, 90))
        }
      }
    }
    add('horizontal-scroll', {
      scrollWidth: de.scrollWidth,
      clientWidth: de.clientWidth,
      culprits: [...new Set(culprits)].slice(0, 6),
    })
  }

  // 2) 觸控目標：規範要求 44×44 以上，並且彼此至少 8px 間距
  const tappable = [...document.querySelectorAll('a, button, select, input, [role="button"]')]
  for (const el of tappable) {
    const r = el.getBoundingClientRect()
    if (r.width <= 1 || r.height <= 1) continue // sr-only 的跳至主要內容是刻意的
    // 勾選框／單選鈕若包在 label 裡，實際可點範圍是整個 label（含文字），
    // 量 input 本身會得到 13×13 這種誤導的數字。
    const box = (el.type === 'checkbox' || el.type === 'radio') && el.closest('label')
      ? el.closest('label').getBoundingClientRect()
      : r
    // 段落內的行內連結不是獨立的觸控目標（規範針對的是可點控制項），
    // 混進來會把真正該修的導覽與按鈕淹掉。
    const inlineInProse = el.tagName === 'A' && el.closest('p, li, td')
    if (inlineInProse) continue
    if (box.height < 44 || box.width < 24) {
      add('touch-target-size', {
        el: `${el.tagName.toLowerCase()}: ${(el.textContent || el.closest('label')?.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 24)}`,
        w: Math.round(box.width),
        h: Math.round(box.height),
      })
    }
  }

  // 3) 表單控制項必須有可存取的名稱
  for (const el of document.querySelectorAll('input, select, textarea')) {
    const id = el.getAttribute('id')
    const labelled =
      (id && document.querySelector(`label[for="${id}"]`)) ||
      el.getAttribute('aria-label') ||
      el.getAttribute('aria-labelledby') ||
      el.closest('label')
    if (!labelled) add('form-labels', { el: el.outerHTML.slice(0, 80) })
  }

  // 4) 標題階層不得跳級，且每頁只有一個 h1
  const levels = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].map((h) =>
    Number(h.tagName[1]),
  )
  const h1s = levels.filter((l) => l === 1).length
  if (h1s !== 1) add('heading-hierarchy', { issue: `h1 數量為 ${h1s}`, levels })
  for (let i = 1; i < levels.length; i += 1) {
    if (levels[i] - levels[i - 1] > 1) {
      add('heading-hierarchy', { issue: `h${levels[i - 1]} 之後直接跳到 h${levels[i]}` })
      break
    }
  }

  // 5) 有意義的圖片需要替代文字
  for (const img of document.querySelectorAll('img')) {
    if (!img.getAttribute('alt') && img.getAttribute('aria-hidden') !== 'true') {
      add('alt-text', { src: (img.getAttribute('src') || '').slice(0, 60) })
    }
  }

  // 6) 寬表格必須自己可橫向捲動，不能把版面撐破
  for (const table of document.querySelectorAll('table')) {
    const wrapper = table.closest('.overflow-x-auto, .overflow-auto, [style*="overflow"]')
    if (!wrapper) {
      const r = table.getBoundingClientRect()
      add('table-overflow', {
        width: Math.round(r.width),
        viewport: de.clientWidth,
        wrapped: false,
      })
    }
  }

  // 7) 內文字級：手機上小於 16px 會觸發 iOS 自動縮放，也難讀
  const bodySize = Number.parseFloat(getComputedStyle(document.body).fontSize)
  out.bodyFontSize = bodySize
  const small = []
  for (const el of document.querySelectorAll('p, li, td, dd, dt, span')) {
    if (!el.textContent || el.textContent.trim().length < 12) continue
    const size = Number.parseFloat(getComputedStyle(el).fontSize)
    if (size < 12) small.push({ size, text: el.textContent.trim().slice(0, 30) })
  }
  if (small.length) add('readable-font-size', { under12px: small.slice(0, 5) })

  // 8) 行長：規範建議桌機 60–75 字、手機 35–60 字。門檻要依斷點分開——
  // 本腳本第一版一律用 48 字，比規範本身還嚴，於是把完全合規的 51–55 字
  // 全報成問題（14 筆假問題）。
  const longLines = []
  for (const el of document.querySelectorAll('p')) {
    const text = (el.textContent || '').trim()
    if (text.length < 40) continue
    const r = el.getBoundingClientRect()
    const size = Number.parseFloat(getComputedStyle(el).fontSize)
    // 中文字寬約等於字級；以此估算每行字數
    const charsPerLine = Math.round(r.width / size)
    const limit = window.innerWidth < 768 ? 60 : 75
    if (charsPerLine > limit) {
      longLines.push({ charsPerLine, limit, text: text.slice(0, 28) })
    }
  }
  if (longLines.length) add('line-length', { lines: longLines.slice(0, 5) })

  // 9) 焦點外框必須在「真的取得焦點時」看得見。
  // 不能只看靜止狀態的 outline——:focus-visible 的正常寫法在靜止時本來就是
  // outline:none，照那樣判會把每個連結都誤報成問題（本腳本第一版就這樣，
  // 一次報出 21 筆假問題）。改為逐一 focus() 後再量。
  for (const el of [...document.querySelectorAll('a, button, input, select')].slice(0, 12)) {
    // 停用的控制項本來就無法聚焦，報它「焦點看不見」是假問題
    // （/workbench 的「抓取真實金流」在未輸入地址前是 disabled，第一版誤報三次）。
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue
    const before = getComputedStyle(el).outlineWidth
    el.focus()
    const after = getComputedStyle(el)
    const visible =
      (after.outlineStyle !== 'none' && Number.parseFloat(after.outlineWidth) >= 1) ||
      after.boxShadow !== 'none'
    if (!visible) {
      add('focus-states', {
        el: `${el.tagName.toLowerCase()}: ${(el.textContent || '').trim().slice(0, 20)}`,
        outlineBefore: before,
        outlineAfter: after.outlineWidth,
      })
    }
    el.blur()
  }

  // 10) 100vh 在手機上會被工具列裁掉，應用 dvh
  for (const el of document.querySelectorAll('[class*="h-screen"], [style*="100vh"]')) {
    add('viewport-units', { el: `${el.tagName.toLowerCase()}.${el.className}`.slice(0, 60) })
    break
  }

  return out
}

const browser = await chromium.launch()
let total = 0
const summary = {}

for (const vp of VIEWPORTS) {
  const ctx = await browser.newContext({
    viewport: { width: vp.width, height: vp.height },
    deviceScaleFactor: 1,
  })
  const page = await ctx.newPage()
  for (const route of ROUTES) {
    await page.goto(base + route, { waitUntil: 'networkidle' })
    await page.waitForTimeout(700)
    const result = await page.evaluate(collect)
    for (const f of result.findings) {
      const key = `${f.rule}`
      summary[key] ??= []
      summary[key].push({ vp: vp.name, route, ...f.detail })
      total += 1
    }
  }
  await ctx.close()
}
await browser.close()

console.log(`基底：${base}`)
console.log(`檢查 ${ROUTES.length} 頁 × ${VIEWPORTS.length} 斷點，共 ${total} 筆發現\n`)
for (const [rule, items] of Object.entries(summary).sort((a, b) => b[1].length - a[1].length)) {
  console.log(`## ${rule}（${items.length} 筆）`)
  for (const item of items.slice(0, 12)) console.log(`  ${JSON.stringify(item)}`)
  if (items.length > 12) console.log(`  …另外 ${items.length - 12} 筆`)
  console.log()
}
if (total === 0) console.log('✓ 未發現問題')
