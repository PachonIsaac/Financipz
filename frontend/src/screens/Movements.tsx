import { useEffect, useMemo, useRef, useState } from 'react'
import { Search, SlidersHorizontal } from 'lucide-react'
import { useTransactionList } from '../api/hooks'
import type { TransactionFilters, TransactionType } from '../api/types'
import { Amount } from '../components/Amount'
import { PageHeader } from '../components/Layout'
import { EmptyState, ErrorState, ListSkeleton } from '../components/states'
import { Button, SelectField, TextField } from '../components/ui'
import { useLookups } from '../features/lookups'
import { TRANSACTION_TYPE_LABELS } from '../features/labels'
import { categoryOptions } from '../features/transactions/display'
import { groupByDay } from '../features/transactions/grouping'
import { TransactionRow } from '../features/transactions/TransactionRow'
import { formatDayHeading } from '../lib/dates'

const QUICK_FILTERS: { label: string; type: TransactionType | '' }[] = [
  { label: 'Todos', type: '' },
  { label: 'Gastos', type: 'expense' },
  { label: 'Ingresos', type: 'income' },
  { label: 'Transferencias', type: 'transfer' },
]

const FILTER_TYPES: TransactionType[] = ['expense', 'income', 'transfer', 'adjustment_in', 'adjustment_out']

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay)
    return () => window.clearTimeout(timer)
  }, [value, delay])
  return debounced
}

export function MovementsScreen() {
  const [text, setText] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [accountId, setAccountId] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [type, setType] = useState<TransactionType | ''>('')
  const [showFilters, setShowFilters] = useState(false)
  const [showSearch, setShowSearch] = useState(false)
  const [pending, setPending] = useState(false)
  const q = useDebounced(text.trim(), 300)

  const filters = useMemo<TransactionFilters>(() => {
    const result: TransactionFilters = {}
    if (q) result.q = q
    if (from) result.from = from
    if (to) result.to = to
    if (accountId) result.account_id = accountId
    if (categoryId) result.category_id = categoryId
    if (type) result.type = type
    if (pending) result.status = 'pending_review'
    return result
  }, [q, from, to, accountId, categoryId, type, pending])

  const list = useTransactionList(filters)
  const { accounts, categories, accountsQuery, categoriesQuery } = useLookups()
  const groups = useMemo(() => groupByDay(list.data?.pages.flatMap((p) => p.items) ?? []), [list.data])
  const activeFilters = [from, to, accountId, categoryId].filter(Boolean).length

  const sentinel = useRef<HTMLDivElement>(null)
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = list
  const nextPageError: unknown = list.isFetchNextPageError ? list.error : null
  useEffect(() => {
    const node = sentinel.current
    if (!node || typeof IntersectionObserver === 'undefined' || !hasNextPage) return
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting) && !isFetchingNextPage) void fetchNextPage()
    })
    observer.observe(node)
    return () => observer.disconnect()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  function clearFilters() {
    setFrom('')
    setTo('')
    setAccountId('')
    setCategoryId('')
  }

  return (
    <>
      <PageHeader
        title="Movimientos"
        action={
          <div className="flex gap-2">
            <button
              type="button"
              aria-label="Buscar"
              aria-expanded={showSearch}
              onClick={() => setShowSearch((v) => !v)}
              className="flex size-11 items-center justify-center rounded-full border border-slate-800 bg-slate-900 active:bg-slate-800"
            >
              <Search aria-hidden="true" size={20} strokeWidth={1.75} />
            </button>
            <button
              type="button"
              aria-label={`Filtros${activeFilters ? ` (${activeFilters})` : ''}`}
              aria-expanded={showFilters}
              onClick={() => setShowFilters((v) => !v)}
              className={`flex size-11 items-center justify-center rounded-full border bg-slate-900 active:bg-slate-800 ${activeFilters ? 'border-emerald-500 text-emerald-500' : 'border-slate-800'}`}
            >
              <SlidersHorizontal aria-hidden="true" size={20} strokeWidth={1.75} />
            </button>
          </div>
        }
      />
      {showSearch ? (
        <div className="mb-3">
          <TextField
            label="Buscar"
            type="search"
            placeholder="Comercio o nota"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </div>
      ) : null}
      <div role="group" aria-label="Tipo de movimiento" className="-mx-4 mb-3 flex gap-2 overflow-x-auto px-4">
        {[
          ...QUICK_FILTERS.map((chip) => ({ label: chip.label, active: !pending && type === chip.type, select: () => { setPending(false); setType(chip.type) } })),
          { label: 'Por revisar', active: pending, select: () => { setPending(true); setType('') } },
        ].map((chip) => (
          <button
            key={chip.label}
            type="button"
            aria-pressed={chip.active}
            onClick={chip.select}
            className={`min-h-11 shrink-0 rounded-full border px-4 text-[15px] ${chip.active ? 'border-emerald-500 bg-emerald-500/15 font-semibold text-emerald-500' : 'border-slate-800 bg-slate-900'}`}
          >
            {chip.label}
          </button>
        ))}
      </div>

      {showFilters ? (
        <div className="mb-4 grid grid-cols-2 gap-3 rounded-3xl border border-slate-800 bg-slate-900 p-4">
          <TextField label="Desde" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          <TextField label="Hasta" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
          <SelectField label="Cuenta" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            <option value="">Todas</option>
            {[...accounts.values()].map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </SelectField>
          <SelectField label="Categoría" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
            <option value="">Todas</option>
            {categoryOptions([...categories.values()]).map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </SelectField>
          <SelectField
            label="Tipo"
            value={type}
            onChange={(e) => setType(e.target.value as TransactionType | '')}
          >
            <option value="">Todos</option>
            {FILTER_TYPES.map((t) => (
              <option key={t} value={t}>
                {TRANSACTION_TYPE_LABELS[t]}
              </option>
            ))}
          </SelectField>
          <Button variant="ghost" className="self-end" onClick={clearFilters}>
            Limpiar filtros
          </Button>
          {accountsQuery.isError || categoriesQuery.isError ? (
            <p className="col-span-2 text-sm text-red-600 dark:text-red-400">
              No se pudieron cargar las cuentas o categorías para filtrar.
            </p>
          ) : null}
        </div>
      ) : null}

      {list.isPending ? (
        <ListSkeleton rows={6} label="Cargando los movimientos" />
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => void list.refetch()} />
      ) : groups.length === 0 ? (
        <EmptyState
          title="Sin movimientos"
          description={
            q || activeFilters ? 'Ningún movimiento coincide con los filtros.' : 'Toca + para registrar el primero.'
          }
        />
      ) : (
        <div className="flex flex-col">
          {groups.map((group) => (
            <section key={group.day} aria-label={formatDayHeading(group.day)}>
              <div className="flex items-baseline justify-between gap-2 px-1 pt-3 pb-2 text-[13px] text-slate-400">
                <h2 className="font-semibold tracking-wide uppercase">{formatDayHeading(group.day)}</h2>
                <span className="flex gap-2">
                  {group.totals.map((total) => (
                    <Amount key={total.currency} value={total.amount} currency={total.currency} tone="neutral" />
                  ))}
                </span>
              </div>
              <ul className="rounded-3xl border border-slate-800 bg-slate-900 px-4">
                {group.items.map((tx) => (
                  <TransactionRow key={tx.id} tx={tx} accounts={accounts} categories={categories} />
                ))}
              </ul>
            </section>
          ))}
          <div ref={sentinel} />
          {list.hasNextPage ? (
            <Button variant="secondary" onClick={() => void list.fetchNextPage()} disabled={list.isFetchingNextPage}>
              {list.isFetchingNextPage ? 'Cargando…' : 'Cargar más'}
            </Button>
          ) : null}
          {nextPageError ? <ErrorState error={nextPageError} onRetry={() => void fetchNextPage()} /> : null}
        </div>
      )}
    </>
  )
}
