import { defineConfig } from '@playwright/test'

const API_BASE = process.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

export default defineConfig({
  testDir: './e2e',
  use: { baseURL: 'http://localhost:4173' },
  // CI 上不得沿用既有服務：沿用會讓「上一次用別的參數 build 出來的 preview」
  // 悄悄過關，綠燈不可重現。本機保留沿用以縮短反覆執行的等待。
  webServer: [
    {
      // 後端必須一起起來：前端只在 status 0 或 5xx 時退回離線快照（4xx 是設定
      // 錯誤，刻意不遮蓋），所以沒有後端時三個 demo 頁會停在錯誤訊息上，六支
      // 測試全部逾時失敗——那不是測試壞了，是環境少了一半。
      command:
        'python -m uvicorn smelens.api.main:app --host 127.0.0.1 --port 8000',
      url: 'http://127.0.0.1:8000/ready',
      cwd: '..',
      reuseExistingServer: !process.env.CI,
      timeout: 300_000,
    },
    {
      // VITE_API_BASE 是 build-time 變數，必須在這個 build 進行時就存在——
      // 少了它 API_BASE 會是空字串，請求打到 preview 自己而回 404。
      command: 'npm run build && npm run preview -- --port 4173',
      url: 'http://localhost:4173',
      env: { VITE_API_BASE: API_BASE },
      reuseExistingServer: !process.env.CI,
      timeout: 300_000,
    },
  ],
})
