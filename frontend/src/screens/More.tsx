import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'
import { PageHeader } from '../components/Layout'
import { Button, Card } from '../components/ui'

const LINK =
  'flex min-h-12 items-center justify-between px-1 text-base active:bg-slate-100 dark:active:bg-slate-800'

export function MoreScreen() {
  const auth = useAuth()
  return (
    <>
      <PageHeader title="Más" />
      <div className="flex flex-col gap-4">
        <Card>
          <nav aria-label="Configuración" className="divide-y divide-slate-200 dark:divide-slate-800">
            <Link to="/more/accounts" className={LINK}>
              Cuentas <span aria-hidden="true">›</span>
            </Link>
            <Link to="/more/categories" className={LINK}>
              Categorías <span aria-hidden="true">›</span>
            </Link>
          </nav>
        </Card>
        <Card>
          {auth.email ? <p className="mb-3 truncate text-sm text-slate-500 dark:text-slate-400">{auth.email}</p> : null}
          <Button variant="secondary" className="w-full" onClick={() => void auth.signOut()}>
            Cerrar sesión
          </Button>
        </Card>
      </div>
    </>
  )
}
