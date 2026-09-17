// 把一頁式企劃書算繪成 A4 單頁 PDF。
// 用 web/ 既有的 Playwright，避免為此新增相依。
// 用法（repo 根目錄）： node scripts/render-proposal.mjs
import { chromium } from './../web/node_modules/playwright-core/index.mjs'
import { pathToFileURL } from 'node:url'
import { resolve } from 'node:path'
import { statSync } from 'node:fs'

const src = resolve('docs/proposal/proposal.html')
const out = resolve('docs/proposal/proposal.pdf')
const browser = await chromium.launch()
const page = await browser.newPage()
await page.goto(pathToFileURL(src).href, { waitUntil: 'networkidle' })
await page.pdf({ path: out, format: 'A4', printBackground: true,
  margin: { top: '0', bottom: '0', left: '0', right: '0' } })
// 單頁驗證：A4 在 96dpi 下為 1123px 高，超過即代表溢出成第二頁。
const h = await page.evaluate(() => document.body.scrollHeight)
await page.setViewportSize({ width: 794, height: 1123 })
await page.screenshot({ path: resolve('docs/proposal/preview.png'), fullPage: true })
await browser.close()
console.log(`已產生 ${out}（${statSync(out).size.toLocaleString()} bytes）`)
console.log(`body 高度: ${h} ${h <= 1123 ? '✓ 單頁' : '✗ 溢出，需縮減內容'}`)
if (h > 1123) process.exitCode = 1
