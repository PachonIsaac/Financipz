import type { Account, AccountCreate, AccountType, AccountUpdate, Currency, Identifier } from '../../api/types'
import { parseAmountInput } from '../../lib/money'

export interface AccountFormValues {
  name: string
  type: AccountType
  currency: Currency
  initialBalance: string
  counterparty: string
  key: string
}

export type AccountFormErrors = Partial<Record<keyof AccountFormValues, string>>

export function emptyAccountValues(): AccountFormValues {
  return { name: '', type: 'bank', currency: 'COP', initialBalance: '', counterparty: '', key: '' }
}

export function accountToValues(account: Account): AccountFormValues {
  return {
    name: account.name,
    type: account.type,
    currency: account.currency,
    initialBalance: account.initial_balance.replace('.', ','),
    counterparty: account.counterparty ?? '',
    key: account.key ?? '',
  }
}

interface Parsed {
  name: string
  type: AccountType
  currency: Currency
  initialBalance: string
  counterparty: string | null
  key: string | null
}

export function validateAccountForm(
  values: AccountFormValues,
): { errors: AccountFormErrors; parsed: Parsed | null } {
  const errors: AccountFormErrors = {}
  const name = values.name.trim()
  if (!name) errors.name = 'Escribe el nombre de la cuenta.'
  else if (name.length > 100) errors.name = 'El nombre es demasiado largo.'

  let initialBalance = '0.00'
  if (values.initialBalance.trim() !== '') {
    const parsed = parseAmountInput(values.initialBalance, { allowNegative: true })
    if (parsed === null) errors.initialBalance = 'El saldo inicial no es válido.'
    else initialBalance = parsed
  }

  const counterparty = values.counterparty.trim()
  if (values.type === 'loan' && !counterparty) errors.counterparty = 'Escribe a quién le prestaste.'

  const key = values.key.trim()
  if (/\s/.test(key)) errors.key = 'La llave no puede tener espacios.'

  if (Object.keys(errors).length > 0) return { errors, parsed: null }
  return {
    errors,
    parsed: {
      name,
      type: values.type,
      currency: values.currency,
      initialBalance,
      counterparty: values.type === 'loan' ? counterparty : null,
      key: key ? key.toLowerCase() : null,
    },
  }
}

export function buildAccountCreate(parsed: NonNullable<ReturnType<typeof validateAccountForm>['parsed']>): AccountCreate {
  const body: AccountCreate = {
    name: parsed.name,
    type: parsed.type,
    currency: parsed.currency,
    initial_balance: parsed.initialBalance,
  }
  if (parsed.counterparty) body.counterparty = parsed.counterparty
  if (parsed.key) body.key = parsed.key
  return body
}

export function buildAccountUpdate(
  parsed: NonNullable<ReturnType<typeof validateAccountForm>['parsed']>,
  original: Account,
): AccountUpdate {
  const body: AccountUpdate = {}
  if (parsed.name !== original.name) body.name = parsed.name
  if (parsed.type !== original.type) body.type = parsed.type
  if (parsed.initialBalance !== original.initial_balance) body.initial_balance = parsed.initialBalance
  if (parsed.counterparty !== original.counterparty) body.counterparty = parsed.counterparty
  if (parsed.key !== original.key) body.key = parsed.key
  return body
}

/** Last-digits identifiers must be exactly four digits. Returns an error message or null. */
export function validateIdentifiers(identifiers: Identifier[]): string | null {
  for (const item of identifiers) {
    if (!/^[0-9]{4}$/.test(item.digits)) return 'Cada identificador debe tener exactamente 4 dígitos.'
  }
  return null
}
