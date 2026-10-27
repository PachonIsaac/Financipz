import { useConfirmTransaction, useDiscardTransaction, useTransactionList } from '../api/hooks'
import { errorMessage } from '../api/client'
import { PageHeader } from '../components/Layout'
import { EmptyState, ErrorState, ListSkeleton } from '../components/states'
import { useToast } from '../components/Toast'
import { Button, Card } from '../components/ui'
import { useLookups } from '../features/lookups'
import { TransactionRow } from '../features/transactions/TransactionRow'

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
              <div className="grid grid-cols-2 gap-2 px-1 pb-1">
                <Button
                  variant="secondary"
                  disabled={busy}
                  onClick={() => discard.mutate(tx.id, { onSuccess: () => toast.show('Movimiento descartado') })}
                >
                  Descartar
                </Button>
                <Button
                  disabled={busy}
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
