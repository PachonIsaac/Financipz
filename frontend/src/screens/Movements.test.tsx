import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { account, category, fakeApi, renderWithApp, transaction } from '../test/utils'
import { MovementsScreen } from './Movements'

describe('movements screen', () => {
  it('lists movements, loads the next page with the cursor and applies filters', async () => {
    const user = userEvent.setup()
    const listTransactions = vi.fn(async (_filters: unknown, cursor?: string) =>
      cursor
        ? { items: [transaction({ id: 't2', merchant: 'Segunda página', date: '2026-10-25T15:00:00Z' })], next_cursor: null }
        : { items: [transaction({ id: 't1', merchant: 'Primera página' })], next_cursor: 'abc' },
    )
    const api = fakeApi({
      listTransactions: listTransactions as never,
      listAccounts: vi.fn(async () => [account({ id: 'acc-1', name: 'Cuenta de ahorros' })]),
      listCategories: vi.fn(async () => [category({ id: 'cat-1', name: 'Mercado' })]),
    })
    renderWithApp(<MovementsScreen />, { api })

    expect(await screen.findByText('Primera página')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Cargar más' }))
    expect(await screen.findByText('Segunda página')).toBeInTheDocument()
    expect(listTransactions).toHaveBeenLastCalledWith({}, 'abc')
    expect(screen.queryByRole('button', { name: 'Cargar más' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Filtros/ }))
    await user.selectOptions(screen.getByLabelText('Tipo'), 'income')
    await waitFor(() => expect(listTransactions).toHaveBeenLastCalledWith({ type: 'income' }, undefined))
  })

  it('filters with the chips, including the ones waiting for review', async () => {
    const user = userEvent.setup()
    const listTransactions = vi.fn(async () => ({ items: [], next_cursor: null }))
    const api = fakeApi({
      listTransactions: listTransactions as never,
      listAccounts: vi.fn(async () => []),
      listCategories: vi.fn(async () => []),
    })
    renderWithApp(<MovementsScreen />, { api })

    await user.click(await screen.findByRole('button', { name: 'Gastos' }))
    await waitFor(() => expect(listTransactions).toHaveBeenLastCalledWith({ type: 'expense' }, undefined))

    await user.click(screen.getByRole('button', { name: 'Por revisar' }))
    await waitFor(() => expect(listTransactions).toHaveBeenLastCalledWith({ status: 'pending_review' }, undefined))
    expect(screen.getByRole('button', { name: 'Por revisar' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Gastos' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('shows an empty state', async () => {
    const api = fakeApi({
      listTransactions: vi.fn(async () => ({ items: [], next_cursor: null })),
      listAccounts: vi.fn(async () => []),
      listCategories: vi.fn(async () => []),
    })
    renderWithApp(<MovementsScreen />, { api })
    expect(await screen.findByText('Sin movimientos')).toBeInTheDocument()
  })
})
