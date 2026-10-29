import { useIsMutating } from '@tanstack/react-query'
import { useState } from 'react'
import {
  useConfirmTransaction,
  useDiscardTransaction,
  useMatches,
  useMergeTransaction,
  useTransactionList,
  useUpdateTransaction,
} from '../api/hooks'
import type { Account, Classification, Transaction } from '../api/types'
import { errorMessage } from '../api/client'
import { PageHeader } from '../components/Layout'
import { EmptyState, ErrorState, ListSkeleton } from '../components/states'
import { useToast } from '../components/Toast'
import { Amount } from '../components/Amount'
import { Button, Card, SelectField } from '../components/ui'
import { formatDateTime } from '../lib/dates'
import { SOURCE_LABELS, TRANSACTION_TYPE_LABELS } from '../features/labels'
import { useLookups } from '../features/lookups'
import { TransactionRow } from '../features/transactions/TransactionRow'

const CLASS_LABELS: Record<Classification, string> = {
  expense: 'Un gasto (el dinero salió para siempre)',
  loan: 'Un préstamo',
  payment: 'Pago de una tarjeta',
  own_transfer: 'Una transferencia entre mis cuentas',
}

/** Which of the person's accounts can receive a transfer of each class. */
function destinationsFor(classification: Classification, source: string | null, accounts: Account[]): Account[] {
  return accounts.filter((a) => {
    if (a.archived || a.id === source || a.type === 'system' || a.type === 'exchange') return false
    if (classification === 'loan') return a.type === 'loan'
    if (classification === 'payment') return a.type === 'credit_card'
    return a.type !== 'loan'
  })
}

/** A transfer to somebody else does not count until the person says what it was. */
function ClassifyTransfer({ tx, accounts }: { tx: Transaction; accounts: Account[] }) {
  const toast = useToast()
  const update = useUpdateTransaction(tx.id)
  const [classification, setClassification] = useState<Classification | ''>('')
  const [destination, setDestination] = useState('')
  const needsDestination = classification !== '' && classification !== 'expense'
  const options = classification === '' ? [] : destinationsFor(classification, tx.account_id, accounts)

  return (
    <div className="mt-2 flex flex-col gap-2 px-1 pb-2">
      <p className="text-[13px] text-amber-300">Falta decir qué fue esta transferencia.</p>
      <SelectField
        label="¿Qué fue?"
        value={classification}
        onChange={(e) => {
          setClassification(e.target.value as Classification | '')
          setDestination('')
        }}
      >
        <option value="">Elige una opción</option>
        {(Object.keys(CLASS_LABELS) as Classification[]).map((key) => (
          <option key={key} value={key}>
            {CLASS_LABELS[key]}
          </option>
        ))}
      </SelectField>
      {needsDestination ? (
        <SelectField label="Cuenta de destino" value={destination} onChange={(e) => setDestination(e.target.value)}>
          <option value="">Elige la cuenta</option>
          {options.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </SelectField>
      ) : null}
      {update.error ? (
        <p role="alert" className="text-sm text-red-400">
          {errorMessage(update.error)}
        </p>
      ) : null}
      <Button
        disabled={classification === '' || (needsDestination && !destination) || update.isPending}
        onClick={() =>
          update.mutate(
            needsDestination
              ? { classification: classification as Classification, target_account_id: destination }
              : { classification: 'expense' },
            { onSuccess: () => toast.show('Transferencia clasificada') },
          )
        }
      >
        {update.isPending ? 'Guardando…' : 'Clasificar'}
      </Button>
    </div>
  )
}

/** Movements that look like the same one (same amount, another source, within a day): the person decides. */
function PossibleMatches({ tx }: { tx: Transaction }) {
  const toast = useToast()
  // While any change is being saved, no other card can start one: two joins in opposite directions would drop both.
  const saving = useIsMutating() > 0
  const matches = useMatches(tx.id)
  const merge = useMergeTransaction()
  const [dismissed, setDismissed] = useState(false)
  const found = matches.data ?? []
  if (dismissed || found.length === 0) return null

  return (
    <div className="mt-2 flex flex-col gap-2 rounded-2xl border border-amber-400/35 bg-amber-400/10 p-3">
      <p className="text-[13px] font-medium text-amber-200">
        {found.length === 1 ? 'Parece el mismo movimiento que:' : 'Podría ser el mismo que uno de estos:'}
      </p>
      <ul className="flex flex-col gap-2">
        {found.map((other) => (
          <li key={other.id} className="flex items-center justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate text-sm">{other.merchant || TRANSACTION_TYPE_LABELS[other.type]}</p>
              <p className="text-xs text-slate-400">
                <Amount value={other.amount} currency={other.currency} tone="neutral" /> · {formatDateTime(other.date)} ·{' '}
                {SOURCE_LABELS[other.source]}
              </p>
            </div>
            <Button
              variant="secondary"
              disabled={saving}
              onClick={() =>
                merge.mutate({ id: tx.id, into: other.id }, { onSuccess: () => toast.show('Unidos: se conservó el otro movimiento') })
              }
            >
              Es el mismo
            </Button>
          </li>
        ))}
      </ul>
      {merge.error ? (
        <p role="alert" className="text-sm text-red-400">
          {errorMessage(merge.error)}
        </p>
      ) : null}
      <Button variant="ghost" onClick={() => setDismissed(true)}>
        Es distinto
      </Button>
    </div>
  )
}

/** For a movement that arrived without an account: choose it here before it can be confirmed. */
function AccountPicker({ tx, accounts }: { tx: Transaction; accounts: Account[] }) {
  const toast = useToast()
  const update = useUpdateTransaction(tx.id)
  const [accountId, setAccountId] = useState('')
  // A movement keeps the currency it arrived in.
  const options = accounts.filter((a) => !a.archived && a.currency === tx.currency && a.id !== tx.target_account_id)

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
  const saving = useIsMutating() > 0
  const busy = confirm.isPending || discard.isPending || saving
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
              <PossibleMatches tx={tx} />
              {tx.account_id === null ? <AccountPicker tx={tx} accounts={[...accounts.values()]} /> : null}
              {tx.account_id !== null && tx.type === 'transfer' && tx.target_account_id === null && tx.classification === null ? (
                <ClassifyTransfer tx={tx} accounts={[...accounts.values()]} />
              ) : null}
              <div className="grid grid-cols-2 gap-2 px-1 pb-1">
                <Button
                  variant="secondary"
                  disabled={busy}
                  onClick={() => discard.mutate(tx.id, { onSuccess: () => toast.show('Movimiento descartado') })}
                >
                  Descartar
                </Button>
                <Button
                  disabled={busy || tx.account_id === null || (tx.type === 'transfer' && tx.target_account_id === null && tx.classification === null)}
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
