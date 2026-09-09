import type { ReactNode } from 'react'

export function Panel({
  title,
  actions,
  children,
}: {
  title?: string
  actions?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="rounded-lg border border-line bg-panel p-5">
      {(title || actions) && (
        <header className="mb-4 flex items-center justify-between gap-4">
          {title && (
            // tabIndex=-1：不進入 Tab 鍵順序（維持原本的鍵盤操作流程不變），但可被
            // 頁面在查詢結果出現後用 .focus() 程式化聚焦——供 FIX 5 的焦點管理使用，
            // 讓螢幕報讀器使用者按下查詢按鈕後，焦點會落到結果的第一個標題上，
            // 不必自己往下找。
            <h2 tabIndex={-1} className="text-base font-semibold text-ink outline-none">
              {title}
            </h2>
          )}
          {actions}
        </header>
      )}
      {children}
    </section>
  )
}
