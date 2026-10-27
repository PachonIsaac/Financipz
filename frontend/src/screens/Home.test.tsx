import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { account, category, fakeApi, renderWithApp, transaction } from '../test/utils'
import { HomeScreen } from './Home'

describe('home screen', () => {
  it('shows balances, recent movements and an empty state when the summary is missing', async () => {
    const api = fakeApi({
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
      getSummary: vi.fn(async () => {
        throw new ApiError(404, 'not_found', 'No encontrado.')
      }),
    })
    renderWithApp(<HomeScreen />, { api })

    expect(await screen.findByText('$ 1.250.000')).toBeInTheDocument()
    expect(screen.getByText('-$ 350.001')).toBeInTheDocument()
    expect(screen.queryByText('Vieja')).not.toBeInTheDocument()
    expect(await screen.findByText('Tienda')).toBeInTheDocument()
    expect(screen.getByText('-$ 45.000')).toBeInTheDocument()
    expect(await screen.findByText('Resumen no disponible')).toBeInTheDocument()
  })

  it('shows an error with retry when accounts fail to load', async () => {
    const api = fakeApi({
      listAccounts: vi.fn(async () => {
        throw new ApiError(0, 'network_error', 'No hay conexión con el servidor.')
      }),
      listCategories: vi.fn(async () => []),
      listTransactions: vi.fn(async () => ({ items: [], next_cursor: null })),
      getSummary: vi.fn(async () => ({})),
    })
    renderWithApp(<HomeScreen />, { api })
    expect((await screen.findAllByText('No hay conexión con el servidor.')).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: 'Reintentar' }).length).toBeGreaterThan(0)
  })

  it('shows month totals when the summary is available', async () => {
    const api = fakeApi({
      listAccounts: vi.fn(async () => []),
      listCategories: vi.fn(async () => []),
      listTransactions: vi.fn(async () => ({ items: [], next_cursor: null })),
      getSummary: vi.fn(async () => ({ income: '3000000.00', expenses: '1200000.00', balance: '1800000.00' })),
    })
    renderWithApp(<HomeScreen />, { api })
    expect(await screen.findByText('+$ 3.000.000')).toBeInTheDocument()
    expect(screen.getByText('-$ 1.200.000')).toBeInTheDocument()
    expect(screen.getByText('$ 1.800.000')).toBeInTheDocument()
  })
})
