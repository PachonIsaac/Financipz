import { useMemo } from 'react'
import { ChevronRight, CreditCard, Tag } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'
import { PageHeader } from '../components/Layout'
import { Button, Card } from '../components/ui'
import { IconChip } from '../features/appearance'
import { formatDateTime } from '../lib/dates'
import { readWakeUps } from '../lib/warmup'

const LINK =
  'flex min-h-[60px] items-center justify-between px-1 text-base active:bg-slate-800'

/** How long the server took to wake up the last times, to judge whether the wait is acceptable. */
function WakeUpSummary() {
  const wakeUps = useMemo(() => readWakeUps(), [])
  const last = wakeUps.at(-1)
  if (!last) {
    return <p className="mb-3 text-sm text-slate-500 dark:text-slate-400">Aún no hay despertares del servidor registrados.</p>
  }
  const recent = wakeUps.slice(-5)
  const average = Math.round(recent.reduce((sum, item) => sum + item.seconds, 0) / recent.length)
  return (
    <p className="mb-3 text-sm text-slate-500 dark:text-slate-400">
      Último despertar del servidor: {last.seconds} s ({formatDateTime(last.at)}). Promedio de los últimos{' '}
      {recent.length}: {average} s.
    </p>
  )
}

export function MoreScreen() {
  const auth = useAuth()
  return (
    <>
      <PageHeader title="Más" />
      <div className="flex flex-col gap-4">
        <Card>
          <nav aria-label="Configuración" className="divide-y divide-slate-200 dark:divide-slate-800">
            <Link to="/more/accounts" className={LINK}>
              <span className="flex items-center gap-3">
                <IconChip icon={CreditCard} size={36} />
                Cuentas
              </span>
              <ChevronRight aria-hidden="true" size={20} className="text-slate-500" />
            </Link>
            <Link to="/more/categories" className={LINK}>
              <span className="flex items-center gap-3">
                <IconChip icon={Tag} size={36} />
                Categorías
              </span>
              <ChevronRight aria-hidden="true" size={20} className="text-slate-500" />
            </Link>
          </nav>
        </Card>
        <Card>
          <WakeUpSummary />
          {auth.email ? <p className="mb-3 truncate text-sm text-slate-500 dark:text-slate-400">{auth.email}</p> : null}
          <Button variant="secondary" className="w-full" onClick={() => void auth.signOut()}>
            Cerrar sesión
          </Button>
        </Card>
      </div>
    </>
  )
}
