import { describe, expect, it } from 'vitest'
import type { Account, Transaction } from '../../api/types'
import { buildUpdate, emptyFormValues, validateTransactionForm } from './form'

function account(id: string, currency: 'COP' | 'USD' = 'COP'): Account {
  return {
    id,
    name: `Cuenta ${id}`,
    type: 'bank',
    currency,
    initial_balance: '0.00',
    counterparty: null,
    key: null,
    archived: false,
    balance: '0.00',
  }
}

const accounts = [account('a'), account('b'), account('usd', 'USD')]
const now = new Date('2026-10-26T19:00:00Z')
const base = { ...emptyFormValues('2026-10-26', 'a'), amount: '45.000' }

describe('validateTransactionForm', () => {
  it('builds an expense payload with money as a decimal string', () => {
    const { errors, payload } = validateTransactionForm(
      { ...base, categoryId: 'cat', merchant: '  Tienda  ' },
      accounts,
      now,
    )
    expect(errors).toEqual({})
    expect(payload).toEqual({
      account_id: 'a',
      type: 'expense',
      amount: '45000.00',
      date: '2026-10-26T14:00:00',
      category_id: 'cat',
      merchant: 'Tienda',
    })
  })

  it('requires an amount', () => {
    const { errors, payload } = validateTransactionForm({ ...base, amount: '' }, accounts, now)
    expect(errors.amount).toBe('Escribe el monto.')
    expect(payload).toBeNull()
  })

  it('rejects zero and malformed amounts', () => {
    expect(validateTransactionForm({ ...base, amount: '0' }, accounts, now).errors.amount).toMatch(/mayor que cero/)
    expect(validateTransactionForm({ ...base, amount: '1,2,3' }, accounts, now).errors.amount).toMatch(/no es válido/)
  })

  it('requires an account', () => {
    expect(validateTransactionForm({ ...base, accountId: '' }, accounts, now).errors.accountId).toBeDefined()
  })

  it('requires a different destination for transfers', () => {
    const transfer = { ...base, type: 'transfer' as const }
    expect(validateTransactionForm(transfer, accounts, now).errors.targetAccountId).toBe('Elige la cuenta destino.')
    expect(
      validateTransactionForm({ ...transfer, targetAccountId: 'a' }, accounts, now).errors.targetAccountId,
    ).toMatch(/distinta/)
  })

  it('builds a transfer without category', () => {
    const { payload } = validateTransactionForm(
      { ...base, type: 'transfer', targetAccountId: 'b', categoryId: 'cat' },
      accounts,
      now,
    )
    expect(payload?.target_account_id).toBe('b')
    expect(payload?.category_id).toBeUndefined()
    expect(payload?.target_amount).toBeUndefined()
  })

  it('accepts a received amount only between currencies', () => {
    const cross = validateTransactionForm(
      { ...base, type: 'transfer', targetAccountId: 'usd', amount: '400.000', targetAmount: '100,50' },
      accounts,
      now,
    )
    expect(cross.payload?.target_amount).toBe('100.50')

    const same = validateTransactionForm(
      { ...base, type: 'transfer', targetAccountId: 'b', targetAmount: '100' },
      accounts,
      now,
    )
    expect(same.payload?.target_amount).toBeUndefined()

    const bad = validateTransactionForm(
      { ...base, type: 'transfer', targetAccountId: 'usd', targetAmount: 'xx' },
      accounts,
      now,
    )
    expect(bad.errors.targetAmount).toBeDefined()
  })

  it('rejects an invalid date and overlong notes', () => {
    const { errors } = validateTransactionForm({ ...base, date: '', note: 'x'.repeat(501) }, accounts, now)
    expect(errors.date).toBeDefined()
    expect(errors.note).toBeDefined()
  })
})

describe('buildUpdate', () => {
  const original: Transaction = {
    id: 't1',
    account_id: 'a',
    target_account_id: null,
    target_text: null,
    classification: null,
    category_id: 'cat',
    type: 'expense',
    amount: '45000.00',
    currency: 'COP',
    target_amount: null,
    fx_rate: null,
    date: '2026-10-20T17:00:00Z',
    merchant: 'Tienda',
    note: null,
    source: 'manual',
    source_id: null,
    status: 'confirmed',
    external_reference: null,
    created_at: '2026-10-20T17:00:00Z',
    updated_at: '2026-10-20T17:00:00Z',
  }

  it('sends only the changed fields', () => {
    const { payload } = validateTransactionForm(
      { ...base, amount: '50000', categoryId: 'cat', merchant: 'Tienda', date: '2026-10-20' },
      accounts,
      now,
    )
    expect(buildUpdate(payload!, original)).toEqual({ amount: '50000.00' })
  })

  it('clears the category and note with null', () => {
    const { payload } = validateTransactionForm(
      { ...base, merchant: 'Tienda', date: '2026-10-20', note: 'hola' },
      accounts,
      now,
    )
    expect(buildUpdate(payload!, original)).toEqual({ category_id: null, note: 'hola' })
  })
})

describe('buildUpdate for cross-currency transfers', () => {
  const transfer: Transaction = {
    id: 't2',
    account_id: 'a',
    target_account_id: 'usd',
    target_text: null,
    classification: null,
    category_id: null,
    type: 'transfer',
    amount: '400000.00',
    currency: 'COP',
    target_amount: '100.00',
    fx_rate: '4000.00',
    date: '2026-10-20T17:00:00Z',
    merchant: null,
    note: null,
    source: 'manual',
    source_id: null,
    status: 'confirmed',
    external_reference: null,
    created_at: '2026-10-20T17:00:00Z',
    updated_at: '2026-10-20T17:00:00Z',
  }
  const values = {
    ...emptyFormValues('2026-10-20', 'a'),
    type: 'transfer' as const,
    targetAccountId: 'usd',
    amount: '400000',
    targetAmount: '100',
  }

  it('sends nothing when nothing changed', () => {
    const { payload } = validateTransactionForm(values, accounts, now)
    expect(buildUpdate(payload!, transfer, accounts)).toEqual({})
  })

  it('sends the received amount when the amount changes', () => {
    const { payload } = validateTransactionForm({ ...values, amount: '420000' }, accounts, now)
    expect(buildUpdate(payload!, transfer, accounts)).toEqual({ amount: '420000.00', target_amount: '100.00' })
  })

  it('sends the received amount when the destination changes', () => {
    const other = { ...accounts[2]!, id: 'usd2' }
    const { payload } = validateTransactionForm({ ...values, targetAccountId: 'usd2' }, [...accounts, other], now)
    expect(buildUpdate(payload!, transfer, [...accounts, other])).toEqual({
      target_account_id: 'usd2',
      target_amount: '100.00',
    })
  })
})
