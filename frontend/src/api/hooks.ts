import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query'
import { useApi } from './ApiProvider'
import type {
  AccountCreate,
  AccountUpdate,
  AdjustmentCreate,
  CategoryCreate,
  CategoryType,
  CategoryUpdate,
  Identifier,
  TransactionCreate,
  TransactionFilters,
  TransactionUpdate,
} from './types'

export const keys = {
  accounts: ['accounts'] as const,
  categories: ['categories'] as const,
  transactions: ['transactions'] as const,
  identifiers: (accountId: string) => ['identifiers', accountId] as const,
  wealth: ['wealth'] as const,
  crypto: ['crypto'] as const,
  integrations: ['integrations'] as const,
  shortcutToken: ['shortcut-token'] as const,
  summary: (month: string) => ['summary', month] as const,
}

/** Balances depend on movements and vice versa, so money mutations refresh all of them. */
function refreshMoney(client: QueryClient): Promise<unknown> {
  return Promise.all([
    client.invalidateQueries({ queryKey: keys.accounts }),
    client.invalidateQueries({ queryKey: keys.transactions }),
    client.invalidateQueries({ queryKey: ['summary'] }),
    client.invalidateQueries({ queryKey: keys.wealth }),
  ])
}

export function useAccounts() {
  const api = useApi()
  return useQuery({ queryKey: keys.accounts, queryFn: () => api.listAccounts() })
}

export function useCategories(type?: CategoryType) {
  const api = useApi()
  return useQuery({ queryKey: [...keys.categories, type ?? 'all'], queryFn: () => api.listCategories(type) })
}

export function useTransactionList(filters: TransactionFilters) {
  const api = useApi()
  return useInfiniteQuery({
    queryKey: [...keys.transactions, 'list', filters],
    queryFn: ({ pageParam }) => api.listTransactions(filters, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  })
}

export function useTransaction(id: string, enabled = true) {
  const api = useApi()
  return useQuery({ queryKey: [...keys.transactions, 'detail', id], queryFn: () => api.getTransaction(id), enabled })
}

export function useSummary(month: string) {
  const api = useApi()
  return useQuery({ queryKey: keys.summary(month), queryFn: () => api.getSummary(month) })
}

export function useWealth() {
  const api = useApi()
  return useQuery({ queryKey: keys.wealth, queryFn: () => api.getWealth() })
}

export function useIdentifiers(accountId: string) {
  const api = useApi()
  return useQuery({ queryKey: keys.identifiers(accountId), queryFn: () => api.listIdentifiers(accountId) })
}

export function useCreateTransaction() {
  const api = useApi()
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: TransactionCreate) => api.createTransaction(body),
    onSuccess: () => refreshMoney(client),
  })
}

export function useUpdateTransaction(id: string) {
  const api = useApi()
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: TransactionUpdate) => api.updateTransaction(id, body),
    onSuccess: () => refreshMoney(client),
  })
}

export function useDeleteTransaction() {
  const api = useApi()
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.deleteTransaction(id),
    onSuccess: (_data, id) => {
      // Drop the detail first so the screen never refetches a movement that is gone.
      client.removeQueries({ queryKey: [...keys.transactions, 'detail', id] })
      void refreshMoney(client)
    },
  })
}

export function useConfirmTransaction() {
  const api = useApi()
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.confirmTransaction(id),
    onSuccess: () => refreshMoney(client),
  })
}

export function useDiscardTransaction() {
  const api = useApi()
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.discardTransaction(id),
    onSuccess: () => refreshMoney(client),
  })
}

export function useCreateAccount() {
  const api = useApi()
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: AccountCreate) => api.createAccount(body),
    onSuccess: () => refreshMoney(client),
  })
}

export function useUpdateAccount() {
  const api = useApi()
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: AccountUpdate }) => api.updateAccount(id, body),
    onSuccess: () => refreshMoney(client),
  })
}

export function useAdjustAccount() {
  const api = useApi()
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: AdjustmentCreate }) => api.adjustAccount(id, body),
    onSuccess: () => refreshMoney(client),
  })
}

export function useReplaceIdentifiers() {
  const api = useApi()
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, identifiers }: { id: string; identifiers: Identifier[] }) =>
      api.replaceIdentifiers(id, identifiers),
    onSuccess: (_data, { id }) => client.invalidateQueries({ queryKey: keys.identifiers(id) }),
  })
}

export function useCreateCategory() {
  const api = useApi()
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: CategoryCreate) => api.createCategory(body),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.categories }),
  })
}

export function useUpdateCategory() {
  const api = useApi()
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: CategoryUpdate }) => api.updateCategory(id, body),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.categories }),
  })
}

export function useDeleteCategory() {
  const api = useApi()
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, reassignTo }: { id: string; reassignTo?: string }) => api.deleteCategory(id, reassignTo),
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: keys.categories }),
        client.invalidateQueries({ queryKey: keys.transactions }),
        client.invalidateQueries({ queryKey: ['summary'] }),
      ]),
  })
}

export function useRefreshData() {
  const api = useApi()
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.refreshData(),
    // Even a partial failure may have stored new data.
    onSettled: () => refreshMoney(client),
  })
}

export function usePortfolio() {
  const api = useApi()
  return useQuery({ queryKey: [...keys.crypto, 'portfolio'], queryFn: () => api.getPortfolio() })
}

export function useCryptoHistory(from: string) {
  const api = useApi()
  return useQuery({ queryKey: [...keys.crypto, 'history', from], queryFn: () => api.getCryptoHistory(from) })
}

export function useTrades() {
  const api = useApi()
  return useInfiniteQuery({
    queryKey: [...keys.crypto, 'trades'],
    queryFn: ({ pageParam }) => api.listTrades(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  })
}

export function useIntegrations() {
  const api = useApi()
  return useQuery({ queryKey: keys.integrations, queryFn: () => api.listIntegrations() })
}

/** What a connection change or a read of the exchange can alter. */
function refreshExchange(client: QueryClient): Promise<unknown> {
  return Promise.all([
    client.invalidateQueries({ queryKey: keys.crypto }),
    client.invalidateQueries({ queryKey: keys.integrations }),
    client.invalidateQueries({ queryKey: keys.wealth }),
    client.invalidateQueries({ queryKey: keys.accounts }),
  ])
}

export function useConnectBinance() {
  const api = useApi()
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ apiKey, apiSecret }: { apiKey: string; apiSecret: string }) => api.connectBinance(apiKey, apiSecret),
    onSuccess: () => refreshExchange(client),
  })
}

export function useDisconnectBinance() {
  const api = useApi()
  const client = useQueryClient()
  return useMutation({ mutationFn: () => api.disconnectBinance(), onSuccess: () => refreshExchange(client) })
}

export function useSyncBinance() {
  const api = useApi()
  const client = useQueryClient()
  return useMutation({ mutationFn: () => api.syncBinance(), onSettled: () => refreshExchange(client) })
}

export function useShortcutToken() {
  const api = useApi()
  return useQuery({ queryKey: keys.shortcutToken, queryFn: () => api.getShortcutToken() })
}

export function useRotateShortcutToken() {
  const api = useApi()
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.rotateShortcutToken(),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.shortcutToken }),
  })
}

/** Reading the mail can add pending movements, which the review inbox and its counter must show. */
function refreshMail(client: QueryClient): Promise<unknown> {
  return Promise.all([
    client.invalidateQueries({ queryKey: keys.integrations }),
    client.invalidateQueries({ queryKey: keys.transactions }),
  ])
}

export function useConnectGmail() {
  const api = useApi()
  return useMutation({ mutationFn: () => api.connectGmail() })
}

export function useSyncGmail() {
  const api = useApi()
  const client = useQueryClient()
  return useMutation({ mutationFn: () => api.syncGmail(), onSettled: () => refreshMail(client) })
}

export function useDisconnectGmail() {
  const api = useApi()
  const client = useQueryClient()
  return useMutation({ mutationFn: () => api.disconnectGmail(), onSuccess: () => refreshMail(client) })
}
