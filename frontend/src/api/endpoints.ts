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
  Me,
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

    confirmTransaction: (id: string) => request<Transaction>(`/transactions/${id}/confirm`, { method: 'POST' }),
    discardTransaction: (id: string) => request<Transaction>(`/transactions/${id}/discard`, { method: 'POST' }),

    getSummary: (month: string) => request<Summary>('/summary', { query: { month } }),
    getWealth: () => request<Wealth>('/wealth'),
  }
}

export type Endpoints = ReturnType<typeof createEndpoints>
