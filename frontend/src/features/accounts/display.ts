import type { Account, Wealth } from '../../api/types'

/**
 * What an account is worth for the list. An exchange account has no movements of its own: its worth is the
 * dollar value of the latest snapshot of what it holds, so showing its balance would always read zero.
 */
export function shownBalance(account: Pick<Account, 'type' | 'balance'>, crypto: Wealth['crypto'] | undefined): string {
  if (account.type === 'exchange' && crypto?.value_usd) return crypto.value_usd
  return account.balance
}
