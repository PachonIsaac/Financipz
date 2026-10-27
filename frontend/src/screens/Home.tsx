import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAccounts, useSummary, useTransactionList, useWealth } from '../api/hooks'
import type { CategoryAmount } from '../api/types'
import { Amount } from '../components/Amount'
import { PageHeader } from '../components/Layout'
import { EmptyState, ErrorState, ListSkeleton } from '../components/states'
import { Card } from '../components/ui'
import { useLookups } from '../features/lookups'
import { ACCOUNT_TYPE_LABELS } from '../features/labels'
import { formatMonth, percentOf, shiftMonth, shortMonth } from '../features/summary'
import { TransactionRow } from '../features/transactions/TransactionRow'
import { formatDate, todayLocal } from '../lib/dates'
import { formatMoney, fromCents, toCents } from '../lib/money'

function reportError(error: unknown) {
  return error instanceof ApiError && error.code === 'missing_fx_rate'
    ? 'Falta la TRM para convertir los saldos en dólares. Sincronízala e intenta de nuevo.'
    : null
}

function WealthCard() {
  const wealth = useWealth()
  const data = wealth.data
  const negative = data ? toCents(data.real_money) < 0n : false
  const fxMessage = reportError(wealth.error)

  return (
    <Card>
      <h2 className="mb-2 text-base font-semibold">Dinero real</h2>
      {wealth.isPending ? (
        <ListSkeleton rows={2} label="Cargando el dinero real" />
      ) : fxMessage ? (
        <p role="alert" className="text-sm text-amber-800 dark:text-amber-300">
          {fxMessage}
        </p>
      ) : wealth.isError ? (
        <ErrorState error={wealth.error} onRetry={() => void wealth.refetch()} />
      ) : data ? (
        <>
          <p
            className={`text-3xl font-bold ${negative ? 'text-red-600 dark:text-red-400' : ''}`}
            aria-label={negative ? 'Dinero real negativo' : 'Dinero real'}
          >
            <Amount value={data.real_money} currency="COP" tone="neutral" />
          </p>
          {negative ? (
            <p role="alert" className="mt-1 text-sm text-red-600 dark:text-red-400">
              La deuda de tarjetas supera el dinero disponible.
            </p>
          ) : null}
          <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
            <div>
              <dt className="text-slate-500 dark:text-slate-400">Disponible</dt>
              <dd className="font-semibold">
                <Amount value={data.available} currency="COP" />
              </dd>
            </div>
            <div>
              <dt className="text-slate-500 dark:text-slate-400">Deuda de tarjetas</dt>
              <dd className="font-semibold">
                <Amount value={data.credit_card_debt} currency="COP" />
              </dd>
            </div>
          </dl>
          {data.loans.length > 0 ? (
            <div className="mt-3">
              <h3 className="text-sm font-medium">
                Préstamos por cobrar: <Amount value={data.receivable_loans} currency="COP" />
              </h3>
              <ul className="text-sm text-slate-600 dark:text-slate-400">
                {data.loans.map((loan) => (
                  <li key={loan.account_id} className="flex justify-between">
                    <span>{loan.counterparty ?? 'Sin nombre'}</span>
                    <Amount value={loan.amount} currency="COP" />
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {data.rate ? (
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              TRM {formatMoney(data.rate.value, 'COP', { exact: true })} del {formatDate(data.rate.date)}
            </p>
          ) : null}
        </>
      ) : null}
    </Card>
  )
}

function CategoryBars({ title, items }: { title: string; items: CategoryAmount[] }) {
  if (items.length === 0) return null
  const max = items.reduce((best, item) => (toCents(item.amount) > toCents(best) ? item.amount : best), '0.00')
  return (
    <div className="mt-4">
      <h3 className="mb-1 text-sm font-medium">{title}</h3>
      <ul className="flex flex-col gap-2">
        {items.map((item) => (
          <li key={item.category_id ?? 'none'}>
            <div className="flex justify-between text-sm">
              <span className="truncate">{item.name}</span>
              <Amount value={item.amount} currency="COP" tone="neutral" />
            </div>
            <div className="h-1.5 rounded-full bg-slate-200 dark:bg-slate-800" aria-hidden="true">
              <div
                className="h-1.5 rounded-full bg-emerald-500"
                style={{ width: `${percentOf(item.amount, max)}%` }}
              />
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

function MonthSummaryCard() {
  const [month, setMonth] = useState(() => todayLocal().slice(0, 7))
  const summary = useSummary(month)
  const data = summary.data
  const fxMessage = reportError(summary.error)

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
      ) : fxMessage ? (
        <p role="alert" className="text-sm text-amber-800 dark:text-amber-300">
          {fxMessage}
        </p>
      ) : summary.isError ? (
        <ErrorState error={summary.error} onRetry={() => void summary.refetch()} />
      ) : data ? (
        <>
          <dl className="grid grid-cols-3 gap-2 text-center">
            <div>
              <dt className="text-xs text-slate-500 dark:text-slate-400">Ingresos</dt>
              <dd className="font-semibold">
                <Amount value={data.income} currency="COP" showPlus />
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500 dark:text-slate-400">Gastos</dt>
              <dd className="font-semibold">
                <Amount value={fromCents(-toCents(data.expenses))} currency="COP" />
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500 dark:text-slate-400">Balance</dt>
              <dd className="font-semibold">
                <Amount value={data.balance} currency="COP" />
              </dd>
            </div>
          </dl>
          <CategoryBars title="Gasto por categoría" items={data.expenses_by_category} />
          <CategoryBars title="Ingresos por categoría" items={data.income_by_category} />
          {data.trend.length > 0 ? (
            <div className="mt-4">
              <h3 className="mb-1 text-sm font-medium">Últimos 6 meses</h3>
              <ul className="flex flex-col gap-1 text-sm">
                {data.trend.map((point) => (
                  <li key={point.month} className="flex justify-between">
                    <span className="capitalize">{shortMonth(point.month)}</span>
                    <Amount value={point.balance} currency="COP" />
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      ) : null}
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
        <WealthCard />
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
