import type { Account, ManualTransactionType, Transaction, TransactionCreate, TransactionUpdate } from '../../api/types'
import { dayOf, toApiDate } from '../../lib/dates'
import { isPositive, parseAmountInput } from '../../lib/money'

export interface TransactionFormValues {
  type: ManualTransactionType
  amount: string
  accountId: string
  targetAccountId: string
  targetAmount: string
  categoryId: string
  merchant: string
  note: string
  /** YYYY-MM-DD */
  date: string
}

export type FormField = keyof TransactionFormValues

export type FormErrors = Partial<Record<FormField, string>>

export const MAX_TEXT_LENGTH = 500
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/

export interface ValidationResult {
  errors: FormErrors
  payload: TransactionCreate | null
}

/** Checks the form and, when valid, builds the API payload (money stays a decimal string). */
export function validateTransactionForm(
  values: TransactionFormValues,
  accounts: Account[],
  now: Date = new Date(),
): ValidationResult {
  const errors: FormErrors = {}

  const amount = parseAmountInput(values.amount)
  if (values.amount.trim() === '') {
    errors.amount = 'Escribe el monto.'
  } else if (amount === null) {
    errors.amount = 'El monto no es válido.'
  } else if (!isPositive(amount)) {
    errors.amount = 'El monto debe ser mayor que cero.'
  }

  const source = accounts.find((account) => account.id === values.accountId)
  if (!source) errors.accountId = 'Elige una cuenta.'

  let targetAmount: string | null = null
  let target: Account | undefined
  if (values.type === 'transfer') {
    target = accounts.find((account) => account.id === values.targetAccountId)
    if (!target) {
      errors.targetAccountId = 'Elige la cuenta destino.'
    } else if (target.id === values.accountId) {
      errors.targetAccountId = 'La cuenta destino debe ser distinta de la de origen.'
    }
    if (source && target && source.currency !== target.currency && values.targetAmount.trim() !== '') {
      targetAmount = parseAmountInput(values.targetAmount)
      if (targetAmount === null || !isPositive(targetAmount)) {
        errors.targetAmount = 'El monto recibido no es válido.'
      }
    }
  }

  if (!DATE_PATTERN.test(values.date)) errors.date = 'Elige una fecha válida.'
  if (values.merchant.length > MAX_TEXT_LENGTH) errors.merchant = 'El comercio es demasiado largo.'
  if (values.note.length > MAX_TEXT_LENGTH) errors.note = 'La nota es demasiado larga.'

  if (Object.keys(errors).length > 0 || amount === null) {
    return { errors, payload: null }
  }

  const payload: TransactionCreate = {
    account_id: values.accountId,
    type: values.type,
    amount,
    date: toApiDate(values.date, now),
  }
  const merchant = values.merchant.trim()
  const note = values.note.trim()
  if (merchant) payload.merchant = merchant
  if (note) payload.note = note
  if (values.type === 'transfer') {
    payload.target_account_id = values.targetAccountId
    if (targetAmount) payload.target_amount = targetAmount
  } else if (values.categoryId) {
    payload.category_id = values.categoryId
  }
  return { errors, payload }
}

/** Reduces a full payload to the fields that differ from the stored movement. */
export function buildUpdate(payload: TransactionCreate, original: Transaction): TransactionUpdate {
  const update: TransactionUpdate = {}
  if (payload.account_id !== original.account_id) update.account_id = payload.account_id
  if (payload.amount !== original.amount) update.amount = payload.amount
  if (payload.date && payload.date.slice(0, 10) !== dayOf(original.date)) update.date = payload.date
  if ((payload.category_id ?? null) !== original.category_id) update.category_id = payload.category_id ?? null
  if ((payload.merchant ?? null) !== original.merchant) update.merchant = payload.merchant ?? null
  if ((payload.note ?? null) !== original.note) update.note = payload.note ?? null
  if (original.type === 'transfer') {
    if ((payload.target_account_id ?? null) !== original.target_account_id) {
      update.target_account_id = payload.target_account_id ?? null
    }
    if (payload.target_amount && payload.target_amount !== original.target_amount) {
      update.target_amount = payload.target_amount
    }
  }
  return update
}

export function emptyFormValues(today: string, accountId = ''): TransactionFormValues {
  return {
    type: 'expense',
    amount: '',
    accountId,
    targetAccountId: '',
    targetAmount: '',
    categoryId: '',
    merchant: '',
    note: '',
    date: today,
  }
}

/** Maps API field names from a validation error to the form's field names. */
export function mapApiField(field: string): FormField | null {
  const map: Record<string, FormField> = {
    amount: 'amount',
    account_id: 'accountId',
    target_account_id: 'targetAccountId',
    target_amount: 'targetAmount',
    category_id: 'categoryId',
    merchant: 'merchant',
    note: 'note',
    date: 'date',
  }
  return map[field] ?? null
}
