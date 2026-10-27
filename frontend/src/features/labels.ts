import type { AccountType, CategoryType, IdentifierType, TransactionSource, TransactionType } from '../api/types'

export const ACCOUNT_TYPE_LABELS: Record<AccountType, string> = {
  cash: 'Efectivo',
  bank: 'Cuenta bancaria',
  credit_card: 'Tarjeta de crédito',
  savings: 'Ahorros',
  wallet: 'Billetera digital',
  exchange: 'Plataforma de cripto',
  loan: 'Préstamo por cobrar',
  system: 'Sistema',
}

/** Types a user can pick when creating or editing an account. */
export const SELECTABLE_ACCOUNT_TYPES: AccountType[] = [
  'cash',
  'bank',
  'savings',
  'wallet',
  'credit_card',
  'exchange',
  'loan',
]

export const TRANSACTION_TYPE_LABELS: Record<TransactionType, string> = {
  expense: 'Gasto',
  income: 'Ingreso',
  transfer: 'Transferencia',
  adjustment_in: 'Ajuste de entrada',
  adjustment_out: 'Ajuste de salida',
}

export const CATEGORY_TYPE_LABELS: Record<CategoryType, string> = {
  expense: 'Gastos',
  income: 'Ingresos',
  transfer: 'Transferencias',
}

export const SOURCE_LABELS: Record<TransactionSource, string> = {
  manual: 'Manual',
  gmail: 'Correo',
  sms_uala: 'SMS',
  wallet: 'Wallet',
  binance: 'Binance',
  myfinance_import: 'Importado',
}

export const IDENTIFIER_TYPE_LABELS: Record<IdentifierType, string> = {
  account: 'Cuenta',
  debit: 'Débito',
  credit: 'Crédito',
}

export const STATUS_LABELS = {
  pending_review: 'Pendiente',
  confirmed: 'Confirmado',
  discarded: 'Descartado',
} as const
