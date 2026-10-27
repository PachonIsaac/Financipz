import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAccounts, useCategories, useDeleteTransaction, useTransaction, useUpdateTransaction } from '../api/hooks'
import type { Transaction } from '../api/types'
import { Amount } from '../components/Amount'
import { PageHeader } from '../components/Layout'
import { ErrorState, FormError, ListSkeleton } from '../components/states'
import { useToast } from '../components/Toast'
import { Badge, Button, Card } from '../components/ui'
import { SOURCE_LABELS, STATUS_LABELS, TRANSACTION_TYPE_LABELS } from '../features/labels'
import { directionOf, signedAmount } from '../features/transactions/display'
import { buildUpdate, type TransactionFormValues } from '../features/transactions/form'
import { TransactionForm } from '../features/transactions/TransactionForm'
import { dayOf, formatDateTime } from '../lib/dates'

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2">
      <dt className="text-sm text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="text-right text-base">{children}</dd>
    </div>
  )
}

function initialValues(tx: Transaction): TransactionFormValues {
  return {
    type: tx.type === 'income' || tx.type === 'transfer' ? tx.type : 'expense',
    amount: tx.amount.replace('.', ','),
    accountId: tx.account_id,
    targetAccountId: tx.target_account_id ?? '',
    targetAmount: tx.target_amount ? tx.target_amount.replace('.', ',') : '',
    categoryId: tx.category_id ?? '',
    merchant: tx.merchant ?? '',
    note: tx.note ?? '',
    date: dayOf(tx.date),
  }
}

export function MovementDetailScreen() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const query = useTransaction(id)
  const accounts = useAccounts()
  const categories = useCategories()
  const update = useUpdateTransaction(id)
  const remove = useDeleteTransaction()
  const [editing, setEditing] = useState(false)
  const [confirmingDelete, setConfirmingDelete] = useState(false)

  const back = { to: '/movements', label: 'Volver a movimientos' }
  const tx = query.data

  if (query.isPending) {
    return (
      <>
        <PageHeader title="Movimiento" back={back} />
        <ListSkeleton rows={4} />
      </>
    )
  }
  if (query.isError || !tx) {
    const notFound = query.error instanceof ApiError && query.error.status === 404
    return (
      <>
        <PageHeader title="Movimiento" back={back} />
        {notFound ? (
          <p role="alert" className="p-6 text-center">
            Este movimiento ya no existe.
          </p>
        ) : (
          <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        )}
      </>
    )
  }

  const accountList = accounts.data ?? []
  const account = accountList.find((a) => a.id === tx.account_id)
  const target = accountList.find((a) => a.id === tx.target_account_id)
  const category = (categories.data ?? []).find((c) => c.id === tx.category_id)
  const editable = tx.type === 'expense' || tx.type === 'income' || tx.type === 'transfer'
  const direction = directionOf(tx.type)

  if (editing && editable) {
    return (
      <>
        <PageHeader
          title="Editar movimiento"
          action={
            <Button variant="ghost" onClick={() => setEditing(false)}>
              Cancelar
            </Button>
          }
        />
        <TransactionForm
          accounts={accountList.filter((a) => !a.archived || a.id === tx.account_id || a.id === tx.target_account_id)}
          categories={categories.data ?? []}
          initial={initialValues(tx)}
          submitLabel="Guardar cambios"
          pending={update.isPending}
          error={update.error}
          lockType
          onSubmit={(payload) => {
            const changes = buildUpdate(payload, tx)
            if (Object.keys(changes).length === 0) {
              setEditing(false)
              return
            }
            update.mutate(changes, {
              onSuccess: () => {
                toast.show('Cambios guardados')
                setEditing(false)
              },
            })
          }}
        />
      </>
    )
  }

  return (
    <>
      <PageHeader title={TRANSACTION_TYPE_LABELS[tx.type]} back={back} />
      <div className="flex flex-col gap-4">
        <Card className="text-center">
          <p className="text-4xl font-bold">
            <Amount
              value={signedAmount(tx)}
              currency={tx.currency}
              exact
              showPlus={direction === 'in'}
              tone={direction === 'neutral' ? 'neutral' : 'auto'}
            />
          </p>
          {tx.merchant ? <p className="mt-1 text-lg">{tx.merchant}</p> : null}
          <div className="mt-2 flex justify-center gap-2">
            {tx.status !== 'confirmed' ? <Badge tone="warning">{STATUS_LABELS[tx.status]}</Badge> : null}
            <Badge>{SOURCE_LABELS[tx.source]}</Badge>
          </div>
        </Card>

        <Card>
          <dl className="divide-y divide-slate-200 dark:divide-slate-800">
            <DetailRow label="Fecha">{formatDateTime(tx.date)}</DetailRow>
            <DetailRow label={tx.type === 'transfer' ? 'Cuenta de origen' : 'Cuenta'}>
              {account?.name ?? '—'}
            </DetailRow>
            {tx.type === 'transfer' ? (
              <DetailRow label="Cuenta destino">{target?.name ?? tx.target_text ?? '—'}</DetailRow>
            ) : null}
            {tx.type === 'transfer' && tx.target_amount && target ? (
              <DetailRow label="Monto recibido">
                <Amount value={tx.target_amount} currency={target.currency} exact tone="neutral" />
              </DetailRow>
            ) : null}
            {tx.type !== 'transfer' ? <DetailRow label="Categoría">{category?.name ?? 'Sin categoría'}</DetailRow> : null}
            {tx.note ? <DetailRow label="Nota">{tx.note}</DetailRow> : null}
          </dl>
        </Card>

        <FormError error={remove.error} />

        {confirmingDelete ? (
          <div
            role="alertdialog"
            aria-labelledby="delete-title"
            className="flex flex-col gap-3 rounded-2xl border border-red-300 p-4 dark:border-red-900"
          >
            <p id="delete-title" className="font-medium">
              ¿Eliminar este movimiento? Esta acción no se puede deshacer.
            </p>
            <div className="grid grid-cols-2 gap-2">
              <Button variant="secondary" onClick={() => setConfirmingDelete(false)}>
                Cancelar
              </Button>
              <Button
                variant="danger"
                disabled={remove.isPending}
                onClick={() =>
                  remove.mutate(tx.id, {
                    onSuccess: () => {
                      toast.show('Movimiento eliminado')
                      void navigate('/movements', { replace: true })
                    },
                  })
                }
              >
                {remove.isPending ? 'Eliminando…' : 'Eliminar'}
              </Button>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            {editable ? (
              <Button variant="secondary" onClick={() => setEditing(true)}>
                Editar
              </Button>
            ) : (
              <span />
            )}
            <Button variant="danger" onClick={() => setConfirmingDelete(true)}>
              Eliminar
            </Button>
          </div>
        )}
      </div>
    </>
  )
}
