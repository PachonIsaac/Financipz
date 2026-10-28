import { useState } from 'react'
import { useConfirmTransaction, useDiscardTransaction, useTransactionList, useUpdateTransaction } from '../api/hooks'
import type { Account, Transaction } from '../api/types'
import { errorMessage } from '../api/client'
import { PageHeader } from '../components/Layout'
import { EmptyState, ErrorState, ListSkeleton } from '../components/states'
import { useToast } from '../components/Toast'
import { Button, Card, SelectField } from '../components/ui'
import { useLookups } from '../features/lookups'
import { TransactionRow } from '../features/transactions/TransactionRow'

/** For a movement that arrived without an account: choose it here before it can be confirmed. */
function AccountPicker({ tx, accounts }: { tx: Transaction; accounts: Account[] }) {
  const toast = useToast()
  const update = useUpdateTransaction(tx.id)
  const [accountId, setAccountId] = useState('')
  // A movement keeps the currency it arrived in.
  const options = accounts.filter((a) => !a.archived && a.currency === tx.currency)

  return (
    <div className="mt-2 flex flex-col gap-2 px-1 pb-2">
      <p className="text-[13px] text-amber-300">No se pudo saber a qué cuenta pertenece.</p>
      <div className="flex items-end gap-2">
        <div className="min-w-0 flex-1">
          <SelectField label="Cuenta" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            <option value="">Elige una cuenta</option>
            {options.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </SelectField>
        </div>
        <Button
          disabled={!accountId || update.isPending}
          onClick={() =>
            update.mutate({ account_id: accountId }, { onSuccess: () => toast.show('Cuenta asignada') })
          }
        >
          {update.isPending ? 'Asignando…' : 'Asignar'}
        </Button>
      </div>
      {update.error ? (
        <p role="alert" className="text-sm text-red-400">
          {errorMessage(update.error)}
        </p>
      ) : null}
    </div>
  )
}

export const PENDING_FILTER = { status: 'pending_review' } as const

export function ReviewScreen() {
  const toast = useToast()
  const list = useTransactionList(PENDING_FILTER)
  const confirm = useConfirmTransaction()
  const discard = useDiscardTransaction()
  const { accounts, categories } = useLookups()
  const items = list.data?.pages.flatMap((p) => p.items) ?? []
  const busy = confirm.isPending || discard.isPending
  const actionError = confirm.error ?? discard.error

  return (
    <>
      <PageHeader title="Revisión" />
      {list.isPending ? (
        <ListSkeleton rows={4} label="Cargando los pendientes" />
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => void list.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState title="Todo al día" description="No tienes movimientos pendientes de revisar." />
      ) : (
        <div className="flex flex-col gap-3">
          {actionError ? (
            <p role="alert" className="rounded-xl bg-red-100 p-3 text-sm text-red-800 dark:bg-red-950 dark:text-red-200">
              {errorMessage(actionError)}
            </p>
          ) : null}
          {items.map((tx) => (
            <Card key={tx.id} className="p-2">
              <ul>
                <TransactionRow tx={tx} accounts={accounts} categories={categories} />
              </ul>
              {tx.account_id === null ? <AccountPicker tx={tx} accounts={[...accounts.values()]} /> : null}
              <div className="grid grid-cols-2 gap-2 px-1 pb-1">
                <Button
                  variant="secondary"
                  disabled={busy}
                  onClick={() => discard.mutate(tx.id, { onSuccess: () => toast.show('Movimiento descartado') })}
                >
                  Descartar
                </Button>
                <Button
                  disabled={busy || tx.account_id === null}
                  onClick={() => confirm.mutate(tx.id, { onSuccess: () => toast.show('Movimiento confirmado') })}
                >
                  Confirmar
                </Button>
              </div>
            </Card>
          ))}
          {list.hasNextPage ? (
            <Button variant="secondary" onClick={() => void list.fetchNextPage()} disabled={list.isFetchingNextPage}>
              {list.isFetchingNextPage ? 'Cargando…' : 'Cargar más'}
            </Button>
          ) : null}
        </div>
      )}
    </>
  )
}
