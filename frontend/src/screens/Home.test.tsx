import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
  // Four decimals, exactly as the API sends it.
  rate: { currency: 'USD', value: '3157.9400', date: '2026-10-25' },
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

  it('shows the balance as the money left after the card debt, with no explanation', async () => {
    renderWithApp(<HomeScreen />, { api: base() })

    expect(await screen.findByLabelText('Balance')).toHaveTextContent('-$ 300.000')
    expect(screen.queryByText('Disponible')).not.toBeInTheDocument()
    expect(screen.queryByText('Dinero real')).not.toBeInTheDocument()
    expect(screen.queryByText(/Deuda de tarjetas/)).not.toBeInTheDocument()
    expect(screen.queryByText(/supera/)).not.toBeInTheDocument()
  })

  it('marks an account that is left out of the balance', async () => {
    const api = base({
      listAccounts: vi.fn(async () => [
        account({ id: 'acc-1', name: 'Cuenta de ahorros' }),
        account({ id: 'acc-2', name: 'Exchange', type: 'exchange', include_in_balance: false }),
      ]),
    })
    renderWithApp(<HomeScreen />, { api })

    expect(await screen.findByText('Fuera del balance')).toBeInTheDocument()
  })

  it('shows month totals and category breakdown', async () => {
    renderWithApp(<HomeScreen />, { api: base() })
    expect(await screen.findByText('+$ 3.000.000')).toBeInTheDocument()
    expect(screen.getAllByText('-$ 1.200.000').length).toBeGreaterThan(0)
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

describe('Home with data shaped like the real API', () => {
  it('shows the exchange rate with four decimals on the wire', async () => {
    renderWithApp(<HomeScreen />, { api: base({ getWealth: vi.fn(async () => wealth), getSummary: vi.fn(async () => summary) }), path: '/' })

    expect(await screen.findByText(/TRM \$ 3\.157,94/)).toBeInTheDocument()
  })

  it('still draws everything when there is no exchange rate yet', async () => {
    const withoutRate: Wealth = { ...wealth, rate: null }
    renderWithApp(<HomeScreen />, { api: base({ getWealth: vi.fn(async () => withoutRate), getSummary: vi.fn(async () => summary) }), path: '/' })

    expect(await screen.findByLabelText('Balance')).toBeInTheDocument()
    expect(screen.queryByText(/TRM/)).not.toBeInTheDocument()
  })

  it('a section that cannot be drawn does not blank the rest of the screen', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const broken: Wealth = { ...wealth, rate: { currency: 'USD', value: 'not-a-rate', date: '2026-10-25' } }
    renderWithApp(<HomeScreen />, { api: base({ getWealth: vi.fn(async () => broken), getSummary: vi.fn(async () => summary) }), path: '/' })

    // The rate line cannot be drawn, and the rest of the screen is still there.
    expect(await screen.findByLabelText('Balance')).toBeInTheDocument()
    expect((await screen.findAllByText('Ingresos')).length).toBeGreaterThan(0)
    expect(await screen.findByText('Cuenta de ahorros')).toBeInTheDocument()
    spy.mockRestore()
  })
})

describe('refreshing the data', () => {
  const result = (overrides = {}) => ({
    fx_rates: { status: 'ok', code: null, message: null },
    binance: { status: 'ok', code: null, message: null },
    ran_at: '2026-10-27T15:00:00Z',
    cached: false,
    ...overrides,
  })

  it('reports each source and reloads the money', async () => {
    const refreshData = vi.fn(async () => result({ binance: { status: 'not_connected', code: 'integration_not_connected', message: 'x' } }))
    const api = base({ refreshData })
    renderWithApp(<HomeScreen />, { api })
    await screen.findByText('Cuenta de ahorros')

    await userEvent.click(screen.getByRole('button', { name: 'Actualizar datos' }))

    expect(await screen.findByText('TRM: actualizada.')).toBeInTheDocument()
    expect(screen.getByText('Binance: no está conectado.')).toBeInTheDocument()
    await waitFor(() => expect(api.getWealth).toHaveBeenCalledTimes(2))
  })

  it('shows what failed and says when nothing was needed', async () => {
    const refreshData = vi.fn(async () =>
      result({ fx_rates: { status: 'error', code: 'fx_source_unavailable', message: 'No se pudo consultar la TRM.' }, cached: true }),
    )
    renderWithApp(<HomeScreen />, { api: base({ refreshData }) })
    await screen.findByText('Cuenta de ahorros')

    await userEvent.click(screen.getByRole('button', { name: 'Actualizar datos' }))

    expect(await screen.findByText('TRM: no se pudo actualizar (No se pudo consultar la TRM.).')).toBeInTheDocument()
    expect(screen.getByText('Ya estaba al día.')).toBeInTheDocument()
  })

  it('shows the error when the request itself fails', async () => {
    const refreshData = vi.fn(async () => {
      throw new ApiError(0, 'timeout', 'El servidor tardó demasiado en responder. Intenta de nuevo.')
    })
    renderWithApp(<HomeScreen />, { api: base({ refreshData }) })
    await screen.findByText('Cuenta de ahorros')

    await userEvent.click(screen.getByRole('button', { name: 'Actualizar datos' }))

    expect(await screen.findByText('El servidor tardó demasiado en responder. Intenta de nuevo.')).toBeInTheDocument()
  })
})
