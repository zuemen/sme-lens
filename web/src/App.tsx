import { lazy, Suspense, useEffect } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import { warmUp } from './api/client'
import Landing from './pages/Landing'

// FIX 4：Landing 保持 eager import（是首次進站的第一個畫面，不該等 chunk 下載）。
// 其餘五頁改成路由層級 code splitting——Cytoscape/dagre 會跟著各頁一起被拆開，
// 使用者只下載真正瀏覽到的那一頁，不必在載入首頁時就把六頁全部（含圖形函式庫）
// 一次抓完。
const Credit = lazy(() => import('./pages/Credit'))
const Group = lazy(() => import('./pages/Group'))
const EarlyWarn = lazy(() => import('./pages/EarlyWarn'))
const Research = lazy(() => import('./pages/Research'))
const Screening = lazy(() => import('./pages/Screening'))
const Workbench = lazy(() => import('./pages/Workbench'))

const NAV = [
  { to: '/', label: '首頁' },
  { to: '/credit', label: '授信意見書' },
  { to: '/group', label: '集團歸戶' },
  { to: '/earlywarn', label: '貸後早期預警' },
  { to: '/screening', label: '出金審查' },
  { to: '/workbench', label: '金流圖譜' },
  { to: '/research', label: 'AI 模型評估' },
]

export default function App() {
  // 冷啟動實測約 5 秒；趁使用者讀首頁時背景喚醒，按鈕按下去時函式已是熱的。
  useEffect(warmUp, [])

  return (
    <div className="min-h-screen bg-base text-ink">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-ink focus:px-4 focus:py-2 focus:text-base"
      >
        跳至主要內容
      </a>

      <header className="border-b border-line">
        {/* 七個導覽項在手機寬度（390px）塞不進一行。原本用 flex-wrap，結果每個
            標籤被折成「首／頁」「授信／意見／書」這種逐字斷行，而評審多半是掃
            QR 用手機進來的——第一眼就看到壞掉的導覽列。改為水平捲動＋不斷行：
            標籤永遠完整，超出寬度就橫向滑動。 */}
        <nav className="mx-auto flex max-w-6xl items-center gap-4 px-6 py-4">
          <span className="shrink-0 font-semibold">
            企鏡 <span className="text-muted">SME Lens</span>
          </span>
          <div className="nav-scroll flex min-w-0 flex-1 gap-5 overflow-x-auto text-sm">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                // 目前位置不只靠顏色標示，同時加粗並提供 aria-current
                className={({ isActive }) =>
                  `whitespace-nowrap ${isActive ? 'font-semibold text-ink' : 'text-muted'}`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </div>
          <NavLink
            to="/credit"
            className="shrink-0 whitespace-nowrap rounded bg-ink px-4 py-1.5 text-sm font-semibold text-base"
          >
            看 Demo
          </NavLink>
        </nav>
      </header>

      <main id="main" className="mx-auto max-w-6xl px-6 py-8">
        <Suspense fallback={<p className="text-sm text-muted">頁面載入中…</p>}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/screening" element={<Screening />} />
            <Route path="/credit" element={<Credit />} />
            <Route path="/group" element={<Group />} />
          <Route path="/earlywarn" element={<EarlyWarn />} />
            <Route path="/workbench" element={<Workbench />} />
            <Route path="/research" element={<Research />} />
          </Routes>
        </Suspense>
      </main>

      <footer className="border-t border-line px-6 py-6 text-center text-sm text-muted">
        研究用途，非投資或法律建議
      </footer>
    </div>
  )
}
