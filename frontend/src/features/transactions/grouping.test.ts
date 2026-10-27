import { describe, expect, it } from 'vitest'
import type { Transaction } from '../../api/types'
import { groupByDay } from './grouping'

function tx(partial: Partial<Transaction>): Transaction {
  return {
    id: 'x',
    account_id: 'a',
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

describe('groupByDay', () => {
  it('groups by Colombian day and totals confirmed non-transfer movements', () => {
    const groups = groupByDay([
      tx({ id: '1', amount: '2500.50' }),
      tx({ id: '2', type: 'income', amount: '10000.00' }),
      tx({ id: '3', type: 'transfer', amount: '99999.00' }),
      tx({ id: '4', status: 'pending_review', amount: '777.00' }),
      tx({ id: '5', date: '2026-10-25T15:00:00Z', amount: '300.00' }),
    ])
    expect(groups.map((g) => g.day)).toEqual(['2026-10-26', '2026-10-25'])
    expect(groups[0]?.items).toHaveLength(4)
    expect(groups[0]?.totals).toEqual([{ currency: 'COP', amount: '7499.50' }])
    expect(groups[1]?.totals).toEqual([{ currency: 'COP', amount: '-300.00' }])
  })

  it('keeps currencies apart', () => {
    const [group] = groupByDay([tx({ id: '1' }), tx({ id: '2', currency: 'USD', amount: '5.00' })])
    expect(group?.totals).toEqual([
      { currency: 'COP', amount: '-1000.00' },
      { currency: 'USD', amount: '-5.00' },
    ])
  })
})
