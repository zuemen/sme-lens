import { useEffect } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import { warmUp } from './api/client'
import Landing from './pages/Landing'
import Research from './pages/Research'
import Screening from './pages/Screening'
import Workbench from './pages/Workbench'

const NAV = [
  { to: '/', label: '首頁' },
  { to: '/screening', label: '出金審查' },
  { to: '/workbench', label: '金流圖譜' },
  { to: '/research', label: '研究成果' },
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
        <nav className="mx-auto flex max-w-6xl flex-wrap items-center gap-6 px-6 py-4">
          <span className="font-semibold">
            鏈鏡 <span className="text-muted">ChainLens</span>
          </span>
          <div className="flex gap-5 text-sm">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                // 目前位置不只靠顏色標示，同時加粗並提供 aria-current
                className={({ isActive }) =>
                  isActive ? 'font-semibold text-ink' : 'text-muted'
                }
              >
                {item.label}
              </NavLink>
            ))}
          </div>
          <NavLink
            to="/screening"
            className="ml-auto rounded bg-ink px-4 py-1.5 text-sm font-semibold text-base"
          >
            看 Demo
          </NavLink>
        </nav>
      </header>

      <main id="main" className="mx-auto max-w-6xl px-6 py-8">
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/screening" element={<Screening />} />
          <Route path="/workbench" element={<Workbench />} />
          <Route path="/research" element={<Research />} />
        </Routes>
      </main>

      <footer className="border-t border-line px-6 py-6 text-center text-sm text-muted">
        研究用途，非投資或法律建議
      </footer>
    </div>
  )
}
