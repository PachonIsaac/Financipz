import type { ReactNode } from 'react'
import { ChevronLeft, Ellipsis, House, Inbox, List, type LucideIcon, Plus } from 'lucide-react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { useTransactionList } from '../api/hooks'
import { OfflineBanner } from './states'

const TAB_BASE = 'relative flex h-14 flex-1 items-center justify-center rounded-[28px]'
const TAB_IDLE = 'text-[#c9c9cf] font-medium'
const TAB_ACTIVE = 'glass-active text-emerald-400 font-semibold'

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
    <NavLink
      to={to}
      end={end}
      aria-label={badge ? `${label}, ${badge} pendientes` : label}
      className={({ isActive }) => `${TAB_BASE} ${isActive ? TAB_ACTIVE : TAB_IDLE}`}
    >
      <Icon aria-hidden="true" size={26} strokeWidth={1.9} />
      {badge ? (
        <span aria-hidden="true" className="absolute top-0.5 right-3 min-w-[18px] rounded-full bg-emerald-500 px-1 text-center text-[11px] leading-[18px] font-bold text-slate-950">
          {badge}
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
      <main className="flex-1 px-4 pt-[max(1rem,env(safe-area-inset-top))] pb-36">
        <Outlet />
      </main>
      <nav
        aria-label="Navegación principal"
        className="fixed inset-x-0 bottom-0 z-40 px-4 pb-[max(1rem,env(safe-area-inset-bottom))]"
      >
        <div className="mx-auto flex max-w-xl items-center gap-3">
          <div className="glass flex h-[68px] flex-1 items-center rounded-[34px] p-1.5">
            <Tab to="/" label="Inicio" end icon={House} />
            <Tab to="/movements" label="Movimientos" icon={List} />
            <Tab to="/review" label="Revisión" icon={Inbox} badge={first && first.items.length > 0 ? count : undefined} />
            <Tab to="/more" label="Más" icon={Ellipsis} />
          </div>
          <Link
            to="/new"
            aria-label="Registrar movimiento"
            className="glass-accent flex size-[68px] shrink-0 items-center justify-center rounded-full text-slate-950 active:brightness-95"
          >
            <Plus aria-hidden="true" size={28} strokeWidth={2.4} />
          </Link>
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
