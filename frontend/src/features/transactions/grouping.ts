import type { Currency, Transaction } from '../../api/types'
import { dayOf } from '../../lib/dates'
import { fromCents, toCents } from '../../lib/money'
import { signedAmount } from './display'

export interface DayGroup {
  day: string
  items: Transaction[]
  /** Net effect of confirmed non-transfer movements, per currency. */
  totals: { currency: Currency; amount: string }[]
}

/** Groups movements (already newest first) by Colombian calendar day. */
export function groupByDay(items: Transaction[]): DayGroup[] {
  const groups = new Map<string, Transaction[]>()
  for (const tx of items) {
    const day = dayOf(tx.date)
    const list = groups.get(day)
    if (list) list.push(tx)
    else groups.set(day, [tx])
  }
  return [...groups.entries()].map(([day, list]) => {
    const sums = new Map<Currency, bigint>()
    for (const tx of list) {
      if (tx.type === 'transfer' || tx.status !== 'confirmed') continue
      sums.set(tx.currency, (sums.get(tx.currency) ?? 0n) + toCents(signedAmount(tx)))
    }
    return {
      day,
      items: list,
      totals: [...sums.entries()].map(([currency, cents]) => ({ currency, amount: fromCents(cents) })),
    }
  })
}
