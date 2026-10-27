import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import type { Summary, Wealth } from '../api/types'
import { account, category, fakeApi, renderWithApp, transaction } from '../test/utils'
import { HomeScreen } from './Home'

const summary: Summary = {
  month: '2026-10',
  income: '3000000.00',
  expenses: '1200000.00',
  balance: '1800000.00',
  income_by_category: [{ category_id: 'c2', name: 'Sueldo', color: null, amount: '3000000.00' }],
  expenses_by_category: [
    { category_id: 'c1', name: 'Mercado', color: null, amount: '800000.00' },
    { category_id: null, name: 'Sin categoría', color: null, amount: '400000.00' },
  ],
  trend: [{ month: '2026-09', income: '1.00', expenses: '2.00', balance: '-1.00' }],
}

const wealth: Wealth = {
  available: '500000.00',
  credit_card_debt: '800000.00',
  real_money: '-300000.00',
  receivable_loans: '100000.00',
  loans: [{ account_id: 'l1', counterparty: 'Persona de prueba', amount: '100000.00' }],
  accounts: [],
  crypto: { value_usd: null },
  rate: { currency: 'USD', value: '4000.00', date: '2026-10-25' },
}

function base(overrides = {}) {
  return fakeApi({
    listAccounts: vi.fn(async () => [
      account({ id: 'acc-1', name: 'Cuenta de ahorros', balance: '1250000.00' }),
      account({ id: 'acc-2', name: 'Tarjeta', type: 'credit_card', balance: '-350000.50' }),
      account({ id: 'acc-3', name: 'Vieja', archived: true, balance: '5.00' }),
    ]),
    listCategories: vi.fn(async () => [category({ id: 'cat-1', name: 'Mercado' })]),
    listTransactions: vi.fn(async () => ({
      items: [transaction({ id: 't1', merchant: 'Tienda', category_id: 'cat-1', amount: '45000.00' })],
      next_cursor: null,
    })),
    getSummary: vi.fn(async () => summary),
    getWealth: vi.fn(async () => wealth),
    ...overrides,
  })
}

describe('home screen', () => {
  it('shows balances and recent movements', async () => {
    renderWithApp(<HomeScreen />, { api: base() })
    expect(await screen.findByText('$ 1.250.000')).toBeInTheDocument()
    expect(screen.getByText('-$ 350.001')).toBeInTheDocument()
    expect(screen.queryByText('Vieja')).not.toBeInTheDocument()
    expect(await screen.findByText('Tienda')).toBeInTheDocument()
    expect(screen.getByText('-$ 45.000')).toBeInTheDocument()
  })

  it('shows negative real money with an alert', async () => {
    renderWithApp(<HomeScreen />, { api: base() })
    expect(await screen.findByLabelText('Dinero real negativo')).toHaveTextContent('-$ 300.000')
    expect(screen.getByText('La deuda de tarjetas supera el dinero disponible.')).toBeInTheDocument()
    expect(screen.getByText('Persona de prueba')).toBeInTheDocument()
  })

  it('shows month totals and category breakdown', async () => {
    renderWithApp(<HomeScreen />, { api: base() })
    expect(await screen.findByText('+$ 3.000.000')).toBeInTheDocument()
    expect(screen.getByText('-$ 1.200.000')).toBeInTheDocument()
    expect(screen.getByText('$ 1.800.000')).toBeInTheDocument()
    expect(screen.getByText('Gasto por categoría')).toBeInTheDocument()
    expect(screen.getByText('Sin categoría')).toBeInTheDocument()
  })

  it('shows a short message when the exchange rate is missing', async () => {
    const missing = () => {
      throw new ApiError(409, 'missing_fx_rate', 'No hay TRM.')
    }
    renderWithApp(<HomeScreen />, { api: base({ getWealth: vi.fn(async () => missing()), getSummary: vi.fn(async () => missing()) }) })
    expect((await screen.findAllByText(/Falta la TRM/)).length).toBe(2)
  })

  it('shows an error with retry when accounts fail to load', async () => {
    const api = base({
      listAccounts: vi.fn(async () => {
        throw new ApiError(0, 'network_error', 'No hay conexión con el servidor.')
      }),
    })
    renderWithApp(<HomeScreen />, { api })
    expect((await screen.findAllByText('No hay conexión con el servidor.')).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: 'Reintentar' }).length).toBeGreaterThan(0)
  })
})
