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
          {title && <h2 className="text-base font-semibold text-ink">{title}</h2>}
          {actions}
        </header>
      )}
      {children}
    </section>
  )
}
