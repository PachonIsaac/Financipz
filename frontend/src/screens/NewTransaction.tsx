import { Link, useNavigate } from 'react-router-dom'
import { useAccounts, useCategories, useCreateTransaction } from '../api/hooks'
import { EmptyState, ErrorState, ListSkeleton } from '../components/states'
import { useToast } from '../components/Toast'
import { TransactionForm } from '../features/transactions/TransactionForm'
import { emptyFormValues } from '../features/transactions/form'
import { todayLocal } from '../lib/dates'
import { readStored, writeStored } from '../lib/storage'

export const LAST_ACCOUNT_KEY = 'financipz.lastAccountId'

export function NewTransactionScreen() {
  const navigate = useNavigate()
  const toast = useToast()
  const accounts = useAccounts()
  const categories = useCategories()
  const create = useCreateTransaction()

  const usable = (accounts.data ?? []).filter((a) => !a.archived)

  let body
  if (accounts.isPending || categories.isPending) {
    body = <ListSkeleton rows={5} />
  } else if (accounts.isError || categories.isError) {
    body = (
      <ErrorState
        error={accounts.error ?? categories.error}
        onRetry={() => {
          void accounts.refetch()
          void categories.refetch()
        }}
      />
    )
  } else if (usable.length === 0) {
    body = (
      <EmptyState
        title="Necesitas una cuenta"
        description="Crea una cuenta para poder registrar movimientos."
        action={
          <Link to="/more/accounts" className="inline-flex min-h-11 items-center font-medium text-emerald-700 dark:text-emerald-400">
            Ir a cuentas
          </Link>
        }
      />
    )
  } else {
    const last = readStored(LAST_ACCOUNT_KEY)
    const preselected = usable.find((a) => a.id === last)?.id ?? usable[0]?.id ?? ''
    body = (
      <TransactionForm
        accounts={usable}
        categories={categories.data}
        initial={emptyFormValues(todayLocal(), preselected)}
        submitLabel="Guardar"
        pending={create.isPending}
        error={create.error}
        autoFocusAmount
        onSubmit={(payload) =>
          create.mutate(payload, {
            onSuccess: () => {
              writeStored(LAST_ACCOUNT_KEY, payload.account_id)
              toast.show('Movimiento guardado')
              void navigate('/')
            },
          })
        }
      />
    )
  }

  return (
    <div className="mx-auto min-h-dvh max-w-xl px-4 pt-[max(1rem,env(safe-area-inset-top))] pb-[max(2rem,env(safe-area-inset-bottom))]">
      <header className="mb-4 flex min-h-11 items-center justify-between">
        <h1 className="text-2xl font-bold">Nuevo movimiento</h1>
        <Link
          to="/"
          aria-label="Cerrar"
          className="flex size-11 items-center justify-center rounded-xl text-2xl active:bg-slate-200 dark:active:bg-slate-800"
        >
          <span aria-hidden="true">×</span>
        </Link>
      </header>
      {body}
    </div>
  )
}
