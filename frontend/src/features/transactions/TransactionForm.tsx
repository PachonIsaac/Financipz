import { useMemo, useState, type FormEvent } from 'react'
import { ApiError, translateProblem } from '../../api/client'
import type { Account, Category, ManualTransactionType, TransactionCreate } from '../../api/types'
import { Button, SelectField, TextAreaField, TextField } from '../../components/ui'
import { FormError } from '../../components/states'
import { ACCOUNT_TYPE_LABELS, TRANSACTION_TYPE_LABELS } from '../labels'
import { CategoryPicker } from './CategoryPicker'
import { categoryOptions } from './display'
import {
  mapApiField,
  validateTransactionForm,
  type FormErrors,
  type TransactionFormValues,
} from './form'

const TYPES: ManualTransactionType[] = ['expense', 'income', 'transfer']

interface Props {
  accounts: Account[]
  categories: Category[]
  initial: TransactionFormValues
  submitLabel: string
  pending: boolean
  error: unknown
  /** The type of an existing movement cannot change. */
  lockType?: boolean
  autoFocusAmount?: boolean
  onSubmit(payload: TransactionCreate): void
}

export function TransactionForm({
  accounts,
  categories,
  initial,
  submitLabel,
  pending,
  error,
  lockType = false,
  autoFocusAmount = false,
  onSubmit,
}: Props) {
  const [values, setValues] = useState(initial)
  const [errors, setErrors] = useState<FormErrors>({})

  const source = accounts.find((a) => a.id === values.accountId)
  const target = accounts.find((a) => a.id === values.targetAccountId)
  const crossCurrency = values.type === 'transfer' && source && target && source.currency !== target.currency
  const options = useMemo(
    () => (values.type === 'transfer' ? [] : categoryOptions(categories, values.type)),
    [categories, values.type],
  )

  const set = <K extends keyof TransactionFormValues>(key: K, value: TransactionFormValues[K]) =>
    setValues((current) => ({ ...current, [key]: value }))

  const serverErrors: FormErrors = {}
  let serverFallback: unknown = error
  if (error instanceof ApiError && error.fieldProblems.length > 0) {
    for (const problem of error.fieldProblems) {
      const field = mapApiField(problem.field)
      if (field) serverErrors[field] = `Este dato ${translateProblem(problem.problem)}.`
    }
    if (Object.keys(serverErrors).length > 0) serverFallback = null
  }
  const fieldError = (field: keyof TransactionFormValues) => errors[field] ?? serverErrors[field]

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const result = validateTransactionForm(values, accounts)
    setErrors(result.errors)
    if (result.payload) onSubmit(result.payload)
  }

  const currencyLabel = source?.currency ?? ''

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <div role="group" aria-label="Tipo de movimiento" className="grid grid-cols-3 gap-1 rounded-2xl border border-slate-800 bg-slate-900 p-1">
        {TYPES.map((type) => (
          <button
            key={type}
            type="button"
            aria-pressed={values.type === type}
            disabled={lockType && values.type !== type}
            onClick={() => setValues((c) => ({ ...c, type, categoryId: '', targetAccountId: '' }))}
            className={`min-h-11 rounded-xl text-[15px] disabled:opacity-40 ${
              values.type === type ? 'bg-emerald-500 font-semibold text-slate-950' : 'text-slate-400'
            }`}
          >
            {TRANSACTION_TYPE_LABELS[type]}
          </button>
        ))}
      </div>

      <TextField
        label={currencyLabel ? `Monto (${currencyLabel})` : 'Monto'}
        inputMode="decimal"
        autoComplete="off"
        placeholder="0"
        autoFocus={autoFocusAmount}
        value={values.amount}
        onChange={(e) => set('amount', e.target.value)}
        error={fieldError('amount')}
        className="text-2xl font-semibold tabular"
      />

      <SelectField
        label={values.type === 'transfer' ? 'Cuenta de origen' : 'Cuenta'}
        value={values.accountId}
        onChange={(e) => set('accountId', e.target.value)}
        error={fieldError('accountId')}
      >
        <option value="">Elige una cuenta</option>
        {accounts.map((a) => (
          <option key={a.id} value={a.id}>
            {a.name} ({a.currency})
          </option>
        ))}
      </SelectField>

      {values.type === 'transfer' ? (
        <>
          <SelectField
            label="Cuenta destino"
            value={values.targetAccountId}
            onChange={(e) => set('targetAccountId', e.target.value)}
            error={fieldError('targetAccountId')}
          >
            <option value="">Elige la cuenta destino</option>
            {accounts
              .filter((a) => a.id !== values.accountId)
              .map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} ({ACCOUNT_TYPE_LABELS[a.type]}, {a.currency})
                </option>
              ))}
          </SelectField>
          {crossCurrency ? (
            <TextField
              label={`Monto recibido (${target?.currency ?? ''})`}
              hint="Opcional. Si lo dejas vacío se usa la TRM del día."
              inputMode="decimal"
              autoComplete="off"
              value={values.targetAmount}
              onChange={(e) => set('targetAmount', e.target.value)}
              error={fieldError('targetAmount')}
            />
          ) : null}
        </>
      ) : (
        <CategoryPicker
          options={options}
          categories={categories}
          value={values.categoryId}
          onChange={(id) => set('categoryId', id)}
          error={fieldError('categoryId')}
        />
      )}

      <TextField
        label="Comercio (opcional)"
        value={values.merchant}
        onChange={(e) => set('merchant', e.target.value)}
        error={fieldError('merchant')}
        autoComplete="off"
      />
      <TextAreaField
        label="Nota (opcional)"
        value={values.note}
        onChange={(e) => set('note', e.target.value)}
        error={fieldError('note')}
      />
      <TextField
        label="Fecha"
        type="date"
        value={values.date}
        onChange={(e) => set('date', e.target.value)}
        error={fieldError('date')}
      />

      <FormError error={serverFallback} />
      <Button type="submit" disabled={pending}>
        {pending ? 'Guardando…' : submitLabel}
      </Button>
    </form>
  )
}
