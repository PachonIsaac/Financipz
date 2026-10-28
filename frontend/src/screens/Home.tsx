import { useState } from 'react'
import { ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAccounts, useRefreshData, useSummary, useTransactionList, useWealth } from '../api/hooks'
import type { RefreshResult, RefreshStep } from '../api/types'
import { Amount } from '../components/Amount'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { PageHeader } from '../components/Layout'
import { EmptyState, ErrorState, ListSkeleton } from '../components/states'
import { TrendChart } from '../components/TrendChart'
import { Card } from '../components/ui'
import { accountIcon, categoryLook, IconChip, TONES } from '../features/appearance'
import { shownBalance } from '../features/accounts/display'
import { useLookups } from '../features/lookups'
import { ACCOUNT_TYPE_LABELS } from '../features/labels'
import { formatMonth, percentOf, shiftMonth, topCategories } from '../features/summary'
import { TransactionRow } from '../features/transactions/TransactionRow'
import { formatDate, todayLocal } from '../lib/dates'
import { formatRate, fromCents, toCents } from '../lib/money'

function reportError(error: unknown) {
  return error instanceof ApiError && error.code === 'missing_fx_rate'
    ? 'Falta la TRM para convertir los saldos en dólares. Sincronízala e intenta de nuevo.'
    : null
}

function BalanceCard() {
  const wealth = useWealth()
  const data = wealth.data
  const fxMessage = reportError(wealth.error)

  return (
    <Card className="p-5">
      <h2 className="text-sm font-medium text-slate-400">Balance</h2>
      {wealth.isPending ? (
        <ListSkeleton rows={1} label="Cargando el balance" />
      ) : fxMessage ? (
        <p role="alert" className="mt-1 text-sm text-amber-300">
          {fxMessage}
        </p>
      ) : wealth.isError ? (
        <ErrorState error={wealth.error} onRetry={() => void wealth.refetch()} />
      ) : data ? (
        <p className="mt-1 text-[40px] leading-[46px] font-bold tracking-tight" aria-label="Balance">
          <Amount value={data.real_money} currency="COP" />
        </p>
      ) : null}
    </Card>
  )
}

function CategoryBars({ items }: { items: Parameters<typeof topCategories>[0] }) {
  if (items.length === 0) return null
  const shares = topCategories(items)
  const max = shares.reduce((best, item) => (toCents(item.amount) > toCents(best) ? item.amount : best), '0.00')
  return (
    <ul className="mt-1 flex flex-col">
      {shares.map((item) => {
        const look = categoryLook(item.others ? undefined : { name: item.name, icon: null, color: item.color, type: 'expense' })
        return (
          <li key={item.key} className="flex min-h-[52px] items-center gap-3 py-1.5">
            <IconChip icon={look.Icon} color={look.color} size={36} />
            <div className="min-w-0 flex-1">
              <div className="flex justify-between gap-2 text-[15px]">
                <span className="truncate">{item.name}</span>
                <Amount value={item.amount} currency="COP" tone="neutral" className="font-semibold" />
              </div>
              <div className="mt-1.5 h-1.5 rounded-full bg-slate-950" aria-hidden="true">
                <div
                  className="h-1.5 rounded-full"
                  style={{ width: `${percentOf(item.amount, max)}%`, background: look.color }}
                />
              </div>
            </div>
          </li>
        )
      })}
    </ul>
  )
}

function MonthSummaryCard() {
  const [month, setMonth] = useState(() => todayLocal().slice(0, 7))
  const summary = useSummary(month)
  const data = summary.data
  const fxMessage = reportError(summary.error)
  const step = 'flex size-11 items-center justify-center rounded-xl text-slate-400 active:bg-slate-800'

  return (
    <>
      <Card>
        <div className="flex items-center justify-between">
          <button type="button" aria-label="Mes anterior" onClick={() => setMonth((m) => shiftMonth(m, -1))} className={step}>
            <ChevronLeft aria-hidden="true" size={22} />
          </button>
          <h2 className="text-[17px] font-semibold capitalize">{formatMonth(month)}</h2>
          <button type="button" aria-label="Mes siguiente" onClick={() => setMonth((m) => shiftMonth(m, 1))} className={step}>
            <ChevronRight aria-hidden="true" size={22} />
          </button>
        </div>
        {summary.isPending ? (
          <ListSkeleton rows={1} label="Cargando el resumen" />
        ) : fxMessage ? (
          <p role="alert" className="text-sm text-amber-300">
            {fxMessage}
          </p>
        ) : summary.isError ? (
          <ErrorState error={summary.error} onRetry={() => void summary.refetch()} />
        ) : data ? (
          <>
            <dl className="mt-1 grid grid-cols-3 gap-2">
              <div className="rounded-2xl bg-slate-800 px-3 py-2.5">
                <dt className="text-xs text-slate-400">Ingresos</dt>
                <dd className="mt-0.5 text-[15px] font-semibold">
                  <Amount value={data.income} currency="COP" showPlus compact />
                </dd>
              </div>
              <div className="rounded-2xl bg-slate-800 px-3 py-2.5">
                <dt className="text-xs text-slate-400">Gastos</dt>
                <dd className="mt-0.5 text-[15px] font-semibold">
                  <Amount value={fromCents(-toCents(data.expenses))} currency="COP" tone="neutral" compact />
                </dd>
              </div>
              <div className="rounded-2xl bg-slate-800 px-3 py-2.5">
                <dt className="text-xs text-slate-400">Balance</dt>
                <dd className="mt-0.5 text-[15px] font-semibold text-emerald-500">
                  <Amount value={data.balance} currency="COP" tone="neutral" compact />
                </dd>
              </div>
            </dl>
            {data.trend.length > 0 ? (
              <div className="mt-5">
                <h3 className="mb-2 text-[15px] font-semibold">Últimos 6 meses</h3>
                <TrendChart data={data.trend} />
              </div>
            ) : null}
          </>
        ) : null}
      </Card>

      {data && data.expenses_by_category.length > 0 ? (
        <Card className="pb-2">
          <div className="flex items-baseline justify-between">
            <h2 className="text-[17px] font-semibold">Gasto por categoría</h2>
            <span className="text-[13px] text-slate-400">
              <Amount value={fromCents(-toCents(data.expenses))} currency="COP" tone="neutral" />
            </span>
          </div>
          <CategoryBars items={data.expenses_by_category} />
        </Card>
      ) : null}
      {data && data.income_by_category.length > 0 ? (
        <Card className="pb-2">
          <h2 className="text-[17px] font-semibold">Ingresos por categoría</h2>
          <CategoryBars items={data.income_by_category} />
        </Card>
      ) : null}
    </>
  )
}

function stepText(name: string, step: RefreshStep, done: string): string {
  if (step.status === 'ok') return `${name}: ${done}.`
  if (step.status === 'not_connected') return `${name}: no está conectado.`
  return `${name}: no se pudo actualizar${step.message ? ` (${step.message})` : ''}.`
}

function RefreshResultText({ result }: { result: RefreshResult }) {
  return (
    <ul className="-mt-2 mb-4 rounded-2xl bg-slate-900 px-4 py-3 text-sm text-slate-400">
      <li>{stepText('TRM', result.fx_rates, 'actualizada')}</li>
      <li>{stepText('Binance', result.binance, 'actualizado')}</li>
      {result.cached ? <li>Ya estaba al día.</li> : null}
    </ul>
  )
}

function CryptoCard() {
  const wealth = useWealth()
  const crypto = wealth.data?.crypto
  if (!crypto?.value_usd) return null
  return (
    <Link
      to="/crypto"
      aria-label="Cripto"
      className="flex min-h-[72px] items-center gap-3 rounded-3xl border border-slate-800 bg-slate-900 px-4 active:bg-slate-800"
    >
      <IconChip icon={accountIcon('exchange')} />
      <div className="min-w-0 flex-1">
        <p className="text-[13px] text-slate-400">Cripto</p>
        <p className="text-lg font-semibold">
          <Amount value={crypto.value_usd} currency="USD" tone="neutral" />
          {crypto.value_cop ? (
            <span className="ml-2 text-sm font-normal text-slate-400">
              ≈ <Amount value={crypto.value_cop} currency="COP" tone="neutral" compact />
            </span>
          ) : null}
        </p>
      </div>
      <ChevronRight aria-hidden="true" size={20} className="text-slate-500" />
    </Link>
  )
}

function RateLine({ rate }: { rate: { value: string; date: string } | null | undefined }) {
  if (!rate) return null
  return (
    <p className="-mt-3 mb-4 text-[13px] text-slate-400">
      TRM {formatRate(rate.value)} del {formatDate(rate.date)}
    </p>
  )
}

export function HomeScreen() {
  const accounts = useAccounts()
  const wealth = useWealth()
  const refresh = useRefreshData()
  const recent = useTransactionList({})
  const lookups = useLookups()
  const visible = (accounts.data ?? []).filter((a) => !a.archived)
  const latest = (recent.data?.pages[0]?.items ?? []).slice(0, 5)
  const rate = wealth.data?.rate

  return (
    <>
      <PageHeader
        title="Inicio"
        action={
          <button
            type="button"
            aria-label="Actualizar datos"
            disabled={refresh.isPending}
            onClick={() => refresh.mutate()}
            className="flex size-11 items-center justify-center rounded-full border border-slate-800 bg-slate-900 text-emerald-500 active:bg-slate-800 disabled:opacity-60"
          >
            <RefreshCw aria-hidden="true" size={20} strokeWidth={1.75} className={refresh.isPending ? 'animate-spin' : ''} />
          </button>
        }
      />
      <ErrorBoundary quiet>
        <RateLine rate={rate} />
      </ErrorBoundary>
      <div className="flex flex-col gap-4">
        {refresh.data ? <RefreshResultText result={refresh.data} /> : null}
        {refresh.isError ? <ErrorState error={refresh.error} /> : null}
        <ErrorBoundary label="No se pudo mostrar el balance.">
          <BalanceCard />
        </ErrorBoundary>
        <ErrorBoundary label="No se pudo mostrar el resumen del mes.">
          <MonthSummaryCard />
        </ErrorBoundary>

        <Card className="pb-2">
          <div className="mb-1 flex items-center justify-between">
            <h2 className="text-[17px] font-semibold">Cuentas</h2>
            <Link to="/more/accounts" className="flex min-h-11 items-center text-sm font-medium text-emerald-500">
              Administrar
            </Link>
          </div>
          {accounts.isPending ? (
            <ListSkeleton rows={3} label="Cargando las cuentas" />
          ) : accounts.isError ? (
            <ErrorState error={accounts.error} onRetry={() => void accounts.refetch()} />
          ) : visible.length === 0 ? (
            <EmptyState
              title="Aún no tienes cuentas"
              description="Crea tu primera cuenta para empezar a registrar movimientos."
              action={
                <Link to="/more/accounts" className="inline-flex min-h-11 items-center font-medium text-emerald-500">
                  Crear una cuenta
                </Link>
              }
            />
          ) : (
            <ul>
              {visible.map((account) => (
                <li key={account.id} className="flex min-h-[60px] items-center gap-3 border-t border-slate-800 py-2 first:border-t-0">
                  <IconChip icon={accountIcon(account.type)} color={account.include_in_balance ? undefined : TONES.gray} />
                  <div className={`min-w-0 flex-1 ${account.include_in_balance ? '' : 'opacity-70'}`}>
                    <p className="truncate text-base">{account.name}</p>
                    <p className="flex flex-wrap items-center gap-1.5 text-[13px] text-slate-400">
                      {ACCOUNT_TYPE_LABELS[account.type]}
                      {account.include_in_balance ? null : (
                        <span className="rounded-full border border-slate-800 bg-slate-800 px-2 text-[11px] leading-4 font-semibold">
                          Fuera del balance
                        </span>
                      )}
                    </p>
                  </div>
                  <Amount
                    value={shownBalance(account, wealth.data?.crypto)}
                    currency={account.currency}
                    className={`text-base font-semibold ${account.include_in_balance ? '' : 'text-slate-400'}`}
                  />
                </li>
              ))}
            </ul>
          )}
        </Card>
        <ErrorBoundary quiet>
          <CryptoCard />
        </ErrorBoundary>
        <Card className="pb-2">
          <div className="mb-1 flex items-center justify-between">
            <h2 className="text-[17px] font-semibold">Últimos movimientos</h2>
            <Link to="/movements" className="flex min-h-11 items-center text-sm font-medium text-emerald-500">
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
