// Types mirroring the backend REST contract. Money is always a decimal string.

import type { Currency } from '../lib/money'

export type { Currency }

export type AccountType =
  | 'cash'
  | 'bank'
  | 'credit_card'
  | 'savings'
  | 'wallet'
  | 'exchange'
  | 'loan'
  | 'system'

export type CategoryType = 'expense' | 'income' | 'transfer'

export type TransactionType = 'expense' | 'income' | 'transfer' | 'adjustment_in' | 'adjustment_out'

export type ManualTransactionType = 'expense' | 'income' | 'transfer'

export type TransactionStatus = 'pending_review' | 'confirmed' | 'discarded'

export type Classification = 'loan' | 'expense' | 'payment' | 'own_transfer'

export type TransactionSource = 'manual' | 'gmail' | 'sms_uala' | 'wallet' | 'binance' | 'myfinance_import'

export interface Account {
  id: string
  name: string
  type: AccountType
  currency: Currency
  initial_balance: string
  counterparty: string | null
  key: string | null
  archived: boolean
  /** False when the balance is left out of the available money, the card debt and the loans. */
  include_in_balance: boolean
  balance: string
}

export interface AccountCreate {
  name: string
  type: AccountType
  currency: Currency
  initial_balance?: string
  counterparty?: string | null
  key?: string | null
  include_in_balance?: boolean
}

export interface AccountUpdate {
  name?: string
  type?: AccountType
  initial_balance?: string
  counterparty?: string | null
  key?: string | null
  archived?: boolean
  include_in_balance?: boolean
}

export type IdentifierType = 'account' | 'debit' | 'credit'

export interface Identifier {
  digits: string
  type: IdentifierType
}

export interface Category {
  id: string
  parent_id: string | null
  name: string
  type: CategoryType
  icon: string | null
  color: string | null
}

export interface CategoryCreate {
  name: string
  type: CategoryType
  parent_id?: string | null
  icon?: string | null
  color?: string | null
}

export interface CategoryUpdate {
  name?: string
  parent_id?: string | null
  icon?: string | null
  color?: string | null
}

export interface Transaction {
  id: string
  /** Null while an automatic source could not tell the account; such a movement cannot be confirmed yet. */
  account_id: string | null
  target_account_id: string | null
  target_text: string | null
  classification: Classification | null
  category_id: string | null
  type: TransactionType
  amount: string
  currency: Currency
  target_amount: string | null
  fx_rate: string | null
  date: string
  merchant: string | null
  note: string | null
  source: TransactionSource
  source_id: string | null
  status: TransactionStatus
  external_reference: string | null
  created_at: string
  updated_at: string
}

export interface TransactionCreate {
  account_id: string
  type: ManualTransactionType
  amount: string
  date?: string
  category_id?: string | null
  merchant?: string | null
  note?: string | null
  target_account_id?: string | null
  target_amount?: string | null
}

export interface TransactionUpdate {
  account_id?: string
  amount?: string
  date?: string
  category_id?: string | null
  merchant?: string | null
  note?: string | null
  target_account_id?: string | null
  target_amount?: string | null
  classification?: Classification | null
}

export interface TransactionPage {
  items: Transaction[]
  next_cursor: string | null
}

export interface TransactionFilters {
  from?: string
  to?: string
  account_id?: string
  category_id?: string
  type?: TransactionType
  status?: TransactionStatus
  q?: string
}

export interface AdjustmentCreate {
  observed_balance: string
  note: string
  date?: string
}

export interface AdjustmentResult {
  transaction: Transaction | null
  balance: string
}

export interface Me {
  id: string
  email: string | null
}

export interface CategoryAmount {
  category_id: string | null
  name: string
  color: string | null
  amount: string
}

export interface MonthTotals {
  month: string
  income: string
  expenses: string
  balance: string
}

export interface Summary {
  month: string
  income: string
  expenses: string
  balance: string
  income_by_category: CategoryAmount[]
  expenses_by_category: CategoryAmount[]
  trend: MonthTotals[]
}

export interface WealthAccount {
  id: string
  name: string
  type: AccountType
  currency: Currency
  archived: boolean
  include_in_balance: boolean
  balance: string
  balance_cop: string
}

export interface Loan {
  account_id: string
  counterparty: string | null
  amount: string
}

export interface Wealth {
  available: string
  credit_card_debt: string
  real_money: string
  receivable_loans: string
  loans: Loan[]
  accounts: WealthAccount[]
  crypto: { value_usd: string | null; value_cop?: string | null; snapshot_date?: string | null }
  rate: { currency: Currency; value: string; date: string } | null
}

export interface RefreshStep {
  status: 'ok' | 'not_connected' | 'error'
  code: string | null
  message: string | null
}

export interface RefreshResult {
  fx_rates: RefreshStep
  binance: RefreshStep
  ran_at: string
  /** True when the previous result was returned because it was too recent to run again. */
  cached: boolean
}

export interface PortfolioAsset {
  asset: string
  quantity: string
  /** Null when the asset could not be priced. */
  value_usd: string | null
  value_cop: string | null
}

export interface Portfolio {
  snapshot_date: string | null
  total_usd: string | null
  total_cop: string | null
  unpriced_assets: number
  rate: { currency: Currency; value: string; date: string } | null
  assets: PortfolioAsset[]
}

export interface HistoryPoint {
  date: string
  total_usd: string
}

export interface Trade {
  id: string
  account_id: string
  pair: string
  side: 'buy' | 'sell'
  quantity: string
  price: string
  fee: string
  fee_asset: string | null
  executed_at: string
  external_id: string
}

export interface TradePage {
  items: Trade[]
  next_cursor: string | null
}

export interface Notice {
  code: string
  message: string
}

export interface Integration {
  provider: string
  status: 'active' | 'error' | 'disconnected'
  last_synced_at: string | null
  warnings: Notice[]
}

export interface BinanceSyncResult {
  snapshot_date: string
  assets: number
  unpriced_assets: number
  total_usd: string
  new_trades: number
  trades_complete: boolean
  warnings: Notice[]
  last_synced_at: string
}
