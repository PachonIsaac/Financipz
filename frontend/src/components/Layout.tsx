import type { ReactNode } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { OfflineBanner } from './states'

const TAB_BASE = 'flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 text-xs font-medium'
const TAB_IDLE = 'text-slate-500 dark:text-slate-400'
const TAB_ACTIVE = 'text-emerald-700 dark:text-emerald-400'

function Tab({ to, label, end = false, icon }: { to: string; label: string; end?: boolean; icon: string }) {
  return (
    <NavLink to={to} end={end} className={({ isActive }) => `${TAB_BASE} ${isActive ? TAB_ACTIVE : TAB_IDLE}`}>
      <span aria-hidden="true" className="text-lg leading-none">
        {icon}
      </span>
      <span>{label}</span>
    </NavLink>
  )
}

export function AppLayout() {
  return (
    <div className="mx-auto flex min-h-dvh max-w-xl flex-col">
      <OfflineBanner />
      <main className="flex-1 px-4 pt-[max(1rem,env(safe-area-inset-top))] pb-28">
        <Outlet />
      </main>
      <nav
        aria-label="Navegación principal"
        className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-200 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur dark:border-slate-800 dark:bg-slate-950/95"
      >
        <div className="mx-auto flex max-w-xl items-center">
          <Tab to="/" label="Inicio" end icon="⌂" />
          <Tab to="/movements" label="Movimientos" icon="≡" />
          <Link
            to="/new"
            aria-label="Registrar movimiento"
            className="mx-2 -mt-5 flex size-14 shrink-0 items-center justify-center rounded-full bg-emerald-500 text-3xl font-semibold text-slate-950 shadow-lg active:bg-emerald-400"
          >
            <span aria-hidden="true">+</span>
          </Link>
          <Tab to="/review" label="Revisión" icon="✓" />
          <Tab to="/more" label="Más" icon="⋯" />
        </div>
      </nav>
    </div>
  )
}

export function PageHeader({
  title,
  back,
  action,
}: {
  title: string
  back?: { to: string; label: string }
  action?: ReactNode
}) {
  return (
    <header className="mb-4 flex min-h-11 items-center justify-between gap-2">
      <div className="flex min-w-0 items-center gap-2">
        {back ? (
          <Link
            to={back.to}
            aria-label={back.label}
            className="flex size-11 shrink-0 items-center justify-center rounded-xl text-xl active:bg-slate-200 dark:active:bg-slate-800"
          >
            <span aria-hidden="true">‹</span>
          </Link>
        ) : null}
        <h1 className="truncate text-2xl font-bold">{title}</h1>
      </div>
      {action}
    </header>
  )
}
