import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAccounts, useSummary, useTransactionList } from '../api/hooks'
import { Amount } from '../components/Amount'
import { PageHeader } from '../components/Layout'
import { EmptyState, ErrorState, ListSkeleton } from '../components/states'
import { Card } from '../components/ui'
import { useLookups } from '../features/lookups'
import { ACCOUNT_TYPE_LABELS } from '../features/labels'
import { formatMonth, parseSummary, shiftMonth } from '../features/summary'
import { TransactionRow } from '../features/transactions/TransactionRow'
import { todayLocal } from '../lib/dates'

function MonthSummaryCard() {
  const [month, setMonth] = useState(() => todayLocal().slice(0, 7))
  const summary = useSummary(month)
  const parsed = parseSummary(summary.data)
  const unavailable = summary.error instanceof ApiError && summary.error.status < 500 && summary.error.status !== 0

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <button
          type="button"
          aria-label="Mes anterior"
          onClick={() => setMonth((m) => shiftMonth(m, -1))}
          className="flex size-11 items-center justify-center rounded-xl text-xl active:bg-slate-200 dark:active:bg-slate-800"
        >
          ‹
        </button>
        <h2 className="text-base font-semibold capitalize">{formatMonth(month)}</h2>
        <button
          type="button"
          aria-label="Mes siguiente"
          onClick={() => setMonth((m) => shiftMonth(m, 1))}
          className="flex size-11 items-center justify-center rounded-xl text-xl active:bg-slate-200 dark:active:bg-slate-800"
        >
          ›
        </button>
      </div>
      {summary.isPending ? (
        <ListSkeleton rows={1} label="Cargando el resumen" />
      ) : parsed ? (
        <dl className="grid grid-cols-3 gap-2 text-center">
          <div>
            <dt className="text-xs text-slate-500 dark:text-slate-400">Ingresos</dt>
            <dd className="font-semibold">
              <Amount value={parsed.income} currency="COP" showPlus />
            </dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500 dark:text-slate-400">Gastos</dt>
            <dd className="font-semibold">
              <Amount value={`-${parsed.expenses.replace(/^-/, '')}`} currency="COP" />
            </dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500 dark:text-slate-400">Balance</dt>
            <dd className="font-semibold">
              <Amount value={parsed.balance} currency="COP" />
            </dd>
          </div>
        </dl>
      ) : unavailable || summary.isSuccess ? (
        <EmptyState
          title="Resumen no disponible"
          description="El resumen del mes aparecerá aquí cuando esté habilitado."
        />
      ) : (
        <ErrorState error={summary.error} onRetry={() => void summary.refetch()} />
      )}
    </Card>
  )
}

export function HomeScreen() {
  const accounts = useAccounts()
  const recent = useTransactionList({})
  const lookups = useLookups()
  const visible = (accounts.data ?? []).filter((a) => !a.archived)
  const latest = (recent.data?.pages[0]?.items ?? []).slice(0, 5)

  return (
    <>
      <PageHeader title="Inicio" />
      <div className="flex flex-col gap-4">
        <MonthSummaryCard />

        <Card>
          <h2 className="mb-2 text-base font-semibold">Cuentas</h2>
          {accounts.isPending ? (
            <ListSkeleton rows={3} label="Cargando las cuentas" />
          ) : accounts.isError ? (
            <ErrorState error={accounts.error} onRetry={() => void accounts.refetch()} />
          ) : visible.length === 0 ? (
            <EmptyState
              title="Aún no tienes cuentas"
              description="Crea tu primera cuenta para empezar a registrar movimientos."
              action={
                <Link to="/more/accounts" className="inline-flex min-h-11 items-center font-medium text-emerald-700 dark:text-emerald-400">
                  Crear una cuenta
                </Link>
              }
            />
          ) : (
            <ul className="divide-y divide-slate-200 dark:divide-slate-800">
              {visible.map((account) => (
                <li key={account.id} className="flex min-h-12 items-center justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-base">{account.name}</p>
                    <p className="text-sm text-slate-500 dark:text-slate-400">{ACCOUNT_TYPE_LABELS[account.type]}</p>
                  </div>
                  <Amount value={account.balance} currency={account.currency} className="text-base font-semibold" />
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-base font-semibold">Últimos movimientos</h2>
            <Link to="/movements" className="flex min-h-11 items-center text-sm font-medium text-emerald-700 dark:text-emerald-400">
              Ver todos
            </Link>
          </div>
          {recent.isPending ? (
            <ListSkeleton rows={3} label="Cargando los movimientos" />
          ) : recent.isError ? (
            <ErrorState error={recent.error} onRetry={() => void recent.refetch()} />
          ) : latest.length === 0 ? (
            <EmptyState title="Sin movimientos" description="Toca + para registrar el primero." />
          ) : (
            <ul>
              {latest.map((tx) => (
                <TransactionRow key={tx.id} tx={tx} accounts={lookups.accounts} categories={lookups.categories} />
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  )
}
