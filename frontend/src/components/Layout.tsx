import type { ReactNode } from 'react'
import { ChevronLeft, Ellipsis, House, Inbox, List, type LucideIcon, Plus } from 'lucide-react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { useTransactionList } from '../api/hooks'
import { OfflineBanner } from './states'

const TAB_BASE = 'relative flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-medium'
const TAB_IDLE = 'text-slate-500'
const TAB_ACTIVE = 'text-emerald-500 font-semibold'

function Tab({
  to,
  label,
  end = false,
  icon: Icon,
  badge,
}: {
  to: string
  label: string
  end?: boolean
  icon: LucideIcon
  badge?: string | undefined
}) {
  return (
    <NavLink to={to} end={end} className={({ isActive }) => `${TAB_BASE} ${isActive ? TAB_ACTIVE : TAB_IDLE}`}>
      <Icon aria-hidden="true" size={24} strokeWidth={1.9} />
      <span>{label}</span>
      {badge ? (
        <span className="absolute top-1 right-[calc(50%-24px)] min-w-[18px] rounded-full bg-emerald-500 px-1 text-center text-[11px] leading-[18px] font-bold text-slate-950">
          {badge}
          <span className="sr-only"> pendientes</span>
        </span>
      ) : null}
    </NavLink>
  )
}

export function AppLayout() {
  const pending = useTransactionList({ status: 'pending_review' })
  const first = pending.data?.pages[0]
  const count = first ? `${first.items.length}${first.next_cursor ? '+' : ''}` : undefined
  return (
    <div className="mx-auto flex min-h-dvh max-w-xl flex-col">
      <OfflineBanner />
      <main className="flex-1 px-4 pt-[max(1rem,env(safe-area-inset-top))] pb-28">
        <Outlet />
      </main>
      <nav
        aria-label="Navegación principal"
        className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-800 bg-slate-900/95 pb-[env(safe-area-inset-bottom)] backdrop-blur"
      >
        <div className="mx-auto flex max-w-xl items-center">
          <Tab to="/" label="Inicio" end icon={House} />
          <Tab to="/movements" label="Movimientos" icon={List} />
          <Link
            to="/new"
            aria-label="Registrar movimiento"
            className="mx-2 -mt-5 flex size-14 shrink-0 items-center justify-center rounded-full bg-emerald-500 text-slate-950 shadow-[0_6px_18px_rgba(255,138,61,0.35)] active:bg-emerald-400"
          >
            <Plus aria-hidden="true" size={26} strokeWidth={2.4} />
          </Link>
          <Tab to="/review" label="Revisión" icon={Inbox} badge={first && first.items.length > 0 ? count : undefined} />
          <Tab to="/more" label="Más" icon={Ellipsis} />
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
            <ChevronLeft aria-hidden="true" size={26} />
          </Link>
        ) : null}
        <h1 className="truncate text-[32px] leading-[38px] font-bold tracking-tight">{title}</h1>
      </div>
      {action}
    </header>
  )
}
