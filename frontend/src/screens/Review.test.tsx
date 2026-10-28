import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { account, fakeApi, renderWithApp, transaction } from '../test/utils'
import { ReviewScreen } from './Review'

describe('review inbox', () => {
  it('lists pending movements and confirms or discards them', async () => {
    const user = userEvent.setup()
    const listTransactions = vi.fn(async () => ({
      items: [transaction({ id: 'p1', merchant: 'Comercio pendiente', status: 'pending_review', source: 'gmail' })],
      next_cursor: null,
    }))
    const confirmTransaction = vi.fn(async () => transaction({ id: 'p1' }))
    const discardTransaction = vi.fn(async () => transaction({ id: 'p1' }))
    const api = fakeApi({
      listTransactions: listTransactions as never,
      listAccounts: vi.fn(async () => [account({ id: 'acc-1' })]),
      listCategories: vi.fn(async () => []),
      confirmTransaction,
      discardTransaction,
    })
    renderWithApp(<ReviewScreen />, { api })
    expect(await screen.findByText('Comercio pendiente')).toBeInTheDocument()
    expect(listTransactions).toHaveBeenCalledWith({ status: 'pending_review' }, undefined)
    await user.click(screen.getByRole('button', { name: 'Confirmar' }))
    await waitFor(() => expect(confirmTransaction).toHaveBeenCalledWith('p1'))
    await user.click(screen.getByRole('button', { name: 'Descartar' }))
    await waitFor(() => expect(discardTransaction).toHaveBeenCalledWith('p1'))
  })

  it('shows an empty state', async () => {
    const api = fakeApi({
      listTransactions: vi.fn(async () => ({ items: [], next_cursor: null })),
      listAccounts: vi.fn(async () => []),
      listCategories: vi.fn(async () => []),
    })
    renderWithApp(<ReviewScreen />, { api })
    expect(await screen.findByText('Todo al día')).toBeInTheDocument()
  })

  it('asks for the account of a movement that arrived without one, and confirms only after that', async () => {
    const user = userEvent.setup()
    const updateTransaction = vi.fn(async () => transaction({ id: 'p2' }))
    const api = fakeApi({
      listTransactions: vi.fn(async () => ({
        items: [transaction({ id: 'p2', merchant: 'Sin dueño', status: 'pending_review', source: 'gmail', account_id: null })],
        next_cursor: null,
      })) as never,
      listAccounts: vi.fn(async () => [
        account({ id: 'acc-1', name: 'Cuenta de ahorros' }),
        account({ id: 'acc-usd', name: 'Cuenta en dólares', currency: 'USD' }),
      ]),
      listCategories: vi.fn(async () => []),
      updateTransaction: updateTransaction as never,
    })
    renderWithApp(<ReviewScreen />, { api })

    expect(await screen.findByText('Sin dueño')).toBeInTheDocument()
    expect(screen.getByText('Sin cuenta')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirmar' })).toBeDisabled()
    // Only accounts in the currency of the movement are offered.
    expect(screen.queryByRole('option', { name: 'Cuenta en dólares' })).not.toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Cuenta'), 'acc-1')
    await user.click(screen.getByRole('button', { name: 'Asignar' }))

    await waitFor(() => expect(updateTransaction).toHaveBeenCalledWith('p2', { account_id: 'acc-1' }))
  })
})
