import type { ReactElement } from 'react'
import { vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ApiProvider } from '../api/ApiProvider'
import type { Endpoints } from '../api/endpoints'
import type { Account, Category, Transaction } from '../api/types'
import { ToastProvider } from '../components/Toast'

export function fakeApi(overrides: Partial<Endpoints> = {}): Endpoints {
  const unmocked = (name: string) => vi.fn(() => Promise.reject(new Error(`Unmocked endpoint: ${name}`)))
  const base = {
    me: unmocked('me'),
    listAccounts: unmocked('listAccounts'),
    createAccount: unmocked('createAccount'),
    updateAccount: unmocked('updateAccount'),
    adjustAccount: unmocked('adjustAccount'),
    listIdentifiers: unmocked('listIdentifiers'),
    replaceIdentifiers: unmocked('replaceIdentifiers'),
    listCategories: unmocked('listCategories'),
    createCategory: unmocked('createCategory'),
    updateCategory: unmocked('updateCategory'),
    deleteCategory: unmocked('deleteCategory'),
    listTransactions: unmocked('listTransactions'),
    getTransaction: unmocked('getTransaction'),
    createTransaction: unmocked('createTransaction'),
    updateTransaction: unmocked('updateTransaction'),
    deleteTransaction: unmocked('deleteTransaction'),
    getSummary: unmocked('getSummary'),
    getWealth: unmocked('getWealth'),
    refreshData: unmocked('refreshData'),
    getPortfolio: unmocked('getPortfolio'),
    getCryptoHistory: unmocked('getCryptoHistory'),
    listTrades: unmocked('listTrades'),
    listIntegrations: unmocked('listIntegrations'),
    connectBinance: unmocked('connectBinance'),
    disconnectBinance: unmocked('disconnectBinance'),
    syncBinance: unmocked('syncBinance'),
    confirmTransaction: unmocked('confirmTransaction'),
    discardTransaction: unmocked('discardTransaction'),
  }
  return { ...base, ...overrides } as unknown as Endpoints
}

export function renderWithApp(
  ui: ReactElement,
  options: { api: Endpoints; route?: string; path?: string },
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 } } })
  const path = options.path ?? '*'
  return render(
    <QueryClientProvider client={client}>
      <ApiProvider api={options.api}>
        <ToastProvider>
          <MemoryRouter initialEntries={[options.route ?? '/']}>
            <Routes>
              <Route path={path} element={ui} />
              <Route path="*" element={<p>Otra pantalla</p>} />
            </Routes>
          </MemoryRouter>
        </ToastProvider>
      </ApiProvider>
    </QueryClientProvider>,
  )
}

export function account(partial: Partial<Account> & { id: string }): Account {
  return {
    name: 'Cuenta de prueba',
    type: 'bank',
    currency: 'COP',
    initial_balance: '0.00',
    counterparty: null,
    key: null,
    archived: false,
    include_in_balance: true,
    balance: '0.00',
    ...partial,
  }
}

export function category(partial: Partial<Category> & { id: string }): Category {
  return { parent_id: null, name: 'Categoría', type: 'expense', icon: null, color: null, ...partial }
}

export function transaction(partial: Partial<Transaction> & { id: string }): Transaction {
  return {
    account_id: 'acc-1',
    target_account_id: null,
    target_text: null,
    classification: null,
    category_id: null,
    type: 'expense',
    amount: '1000.00',
    currency: 'COP',
    target_amount: null,
    fx_rate: null,
    date: '2026-10-26T15:00:00Z',
    merchant: null,
    note: null,
    source: 'manual',
    source_id: null,
    status: 'confirmed',
    external_reference: null,
    created_at: '2026-10-26T15:00:00Z',
    updated_at: '2026-10-26T15:00:00Z',
    ...partial,
  }
}

/** An in-memory `localStorage`: the one Node provides on its own is unusable in the test environment. */
export function stubLocalStorage(): void {
  const data = new Map<string, string>()
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
    removeItem: (key: string) => void data.delete(key),
    clear: () => data.clear(),
  })
}
