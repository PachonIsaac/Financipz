import type { ApiClient } from './client'
import type {
  Account,
  AccountCreate,
  AccountUpdate,
  AdjustmentCreate,
  AdjustmentResult,
  Category,
  CategoryCreate,
  CategoryType,
  CategoryUpdate,
  Identifier,
  BinanceSyncResult,
  GmailSyncResult,
  HistoryPoint,
  Integration,
  Me,
  Portfolio,
  TradePage,
  RefreshResult,
  Summary,
  Wealth,
  Transaction,
  TransactionCreate,
  TransactionFilters,
  TransactionPage,
  TransactionUpdate,
} from './types'

export const PAGE_SIZE = 30

export function createEndpoints(client: ApiClient) {
  const { request } = client
  return {
    me: () => request<Me>('/me'),

    listAccounts: (archived?: boolean) => request<Account[]>('/accounts', { query: { archived } }),
    createAccount: (body: AccountCreate) => request<Account>('/accounts', { method: 'POST', body }),
    updateAccount: (id: string, body: AccountUpdate) =>
      request<Account>(`/accounts/${id}`, { method: 'PATCH', body }),
    adjustAccount: (id: string, body: AdjustmentCreate) =>
      request<AdjustmentResult>(`/accounts/${id}/adjustments`, { method: 'POST', body }),
    listIdentifiers: (id: string) => request<Identifier[]>(`/accounts/${id}/identifiers`),
    replaceIdentifiers: (id: string, identifiers: Identifier[]) =>
      request<Identifier[]>(`/accounts/${id}/identifiers`, { method: 'PUT', body: { identifiers } }),

    listCategories: (type?: CategoryType) => request<Category[]>('/categories', { query: { type } }),
    createCategory: (body: CategoryCreate) => request<Category>('/categories', { method: 'POST', body }),
    updateCategory: (id: string, body: CategoryUpdate) =>
      request<Category>(`/categories/${id}`, { method: 'PATCH', body }),
    deleteCategory: (id: string, reassignTo?: string) =>
      request<void>(`/categories/${id}`, { method: 'DELETE', query: { reassign_to: reassignTo } }),

    listTransactions: (filters: TransactionFilters, cursor?: string, limit: number = PAGE_SIZE) =>
      request<TransactionPage>('/transactions', { query: { ...filters, cursor, limit } }),
    getTransaction: (id: string) => request<Transaction>(`/transactions/${id}`),
    createTransaction: (body: TransactionCreate) =>
      request<Transaction>('/transactions', { method: 'POST', body }),
    updateTransaction: (id: string, body: TransactionUpdate) =>
      request<Transaction>(`/transactions/${id}`, { method: 'PATCH', body }),
    deleteTransaction: (id: string) => request<void>(`/transactions/${id}`, { method: 'DELETE' }),

    // Movements that may be the same one as a pending movement, and saying that they are.
    listMatches: (id: string) => request<Transaction[]>(`/transactions/${id}/matches`),
    mergeTransaction: (id: string, into: string) =>
      request<Transaction>(`/transactions/${id}/merge`, { method: 'POST', body: { into } }),

    confirmTransaction: (id: string) => request<Transaction>(`/transactions/${id}/confirm`, { method: 'POST' }),
    discardTransaction: (id: string) => request<Transaction>(`/transactions/${id}/discard`, { method: 'POST' }),

    getSummary: (month: string) => request<Summary>('/summary', { query: { month } }),
    getWealth: () => request<Wealth>('/wealth'),

    getPortfolio: () => request<Portfolio>('/crypto/portfolio'),
    getCryptoHistory: (from: string) => request<HistoryPoint[]>('/crypto/history', { query: { from } }),
    listTrades: (cursor?: string) => request<TradePage>('/crypto/trades', { query: { cursor, limit: 20 } }),

    listIntegrations: () => request<Integration[]>('/integrations'),
    connectBinance: (apiKey: string, apiSecret: string) =>
      request<Integration>('/integrations/binance', { method: 'PUT', body: { api_key: apiKey, api_secret: apiSecret } }),
    disconnectBinance: () => request<void>('/integrations/binance', { method: 'DELETE' }),
    // The exchange may be read by a deployment that is asleep, which takes a while to answer.
    syncBinance: () => request<BinanceSyncResult>('/integrations/binance/sync', { method: 'POST', timeoutMs: 160_000 }),

    // The browser cannot send the session on a redirect, so the app asks for the address and opens it.
    connectGmail: () => request<{ authorization_url: string }>('/integrations/gmail/connect', { method: 'POST' }),
    syncGmail: () => request<GmailSyncResult>('/integrations/gmail/sync', { method: 'POST', timeoutMs: 120_000 }),
    disconnectGmail: () => request<void>('/integrations/gmail', { method: 'DELETE' }),

    // Reads the exchange rate and the exchange balances; a sleeping server may need a while.
    refreshData: () => request<RefreshResult>('/refresh', { method: 'POST', timeoutMs: 160_000 }),
  }
}

export type Endpoints = ReturnType<typeof createEndpoints>
