import { useMemo } from 'react'
import { useAccounts, useCategories } from '../api/hooks'
import type { Account, Category } from '../api/types'

/** Accounts and categories indexed by id, for rendering names in lists. */
export function useLookups() {
  const accountsQuery = useAccounts()
  const categoriesQuery = useCategories()
  const accounts = useMemo(
    () => new Map<string, Account>((accountsQuery.data ?? []).map((a) => [a.id, a])),
    [accountsQuery.data],
  )
  const categories = useMemo(
    () => new Map<string, Category>((categoriesQuery.data ?? []).map((c) => [c.id, c])),
    [categoriesQuery.data],
  )
  return { accounts, categories, accountsQuery, categoriesQuery }
}
