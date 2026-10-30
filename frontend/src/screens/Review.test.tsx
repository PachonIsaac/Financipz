import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { account, category, fakeApi, renderWithApp, transaction } from '../test/utils'
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

  it('asks what a transfer to someone else was, and confirms only after it is classified', async () => {
    const user = userEvent.setup()
    const updateTransaction = vi.fn(async () => transaction({ id: 'p3' }))
    const api = fakeApi({
      listTransactions: vi.fn(async () => ({
        items: [transaction({ id: 'p3', type: 'transfer', merchant: null, status: 'pending_review', source: 'gmail', target_text: 'Persona Ejemplo' })],
        next_cursor: null,
      })) as never,
      listAccounts: vi.fn(async () => [
        account({ id: 'acc-1', name: 'Cuenta de ahorros' }),
        account({ id: 'card', name: 'Tarjeta', type: 'credit_card' }),
        account({ id: 'loan', name: 'Préstamo a Ana', type: 'loan' }),
      ]),
      listCategories: vi.fn(async () => []),
      updateTransaction: updateTransaction as never,
    })
    renderWithApp(<ReviewScreen />, { api })

    expect(await screen.findByText('Falta decir qué fue esta transferencia.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirmar' })).toBeDisabled()

    // A card payment needs a card as destination, and only cards are offered.
    await user.selectOptions(screen.getByLabelText('¿Qué fue?'), 'payment')
    expect(screen.queryByRole('option', { name: 'Préstamo a Ana' })).not.toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Cuenta de destino'), 'card')
    await user.click(screen.getByRole('button', { name: 'Clasificar' }))
    await waitFor(() =>
      expect(updateTransaction).toHaveBeenCalledWith('p3', { classification: 'payment', target_account_id: 'card' }),
    )

    // An expense needs no destination.
    await user.selectOptions(screen.getByLabelText('¿Qué fue?'), 'expense')
    expect(screen.queryByLabelText('Cuenta de destino')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Clasificar' }))
    await waitFor(() => expect(updateTransaction).toHaveBeenLastCalledWith('p3', { classification: 'expense' }))
  })

  it('offers the movement it may be the same as, and joins them only when the person says so', async () => {
    const user = userEvent.setup()
    const typed = transaction({ id: 'typed', merchant: 'Supermercado', amount: '86400.00', status: 'confirmed', source: 'manual' })
    const mergeTransaction = vi.fn(async () => typed)
    const listMatches = vi.fn(async (id: string) => (id === 'p9' ? [typed] : []))
    const api = fakeApi({
      listTransactions: vi.fn(async () => ({
        items: [transaction({ id: 'p9', merchant: 'SUPERMERCADO', amount: '86400.00', status: 'pending_review', source: 'gmail' })],
        next_cursor: null,
      })) as never,
      listAccounts: vi.fn(async () => [account({ id: 'acc-1' })]),
      listCategories: vi.fn(async () => []),
      listMatches: listMatches as never,
      mergeTransaction: mergeTransaction as never,
    })
    renderWithApp(<ReviewScreen />, { api })

    expect(await screen.findByText('Parece el mismo movimiento que:')).toBeInTheDocument()
    expect(mergeTransaction).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Es el mismo' }))

    await waitFor(() => expect(mergeTransaction).toHaveBeenCalledWith('p9', 'typed'))
  })

  it('lets the person say it is a different movement, and shows nothing when there is no candidate', async () => {
    const user = userEvent.setup()
    const other = transaction({ id: 'o1', merchant: 'Otro', amount: '10.00', status: 'confirmed', source: 'manual' })
    const api = fakeApi({
      listTransactions: vi.fn(async () => ({
        items: [
          transaction({ id: 'p1', merchant: 'Con candidato', status: 'pending_review', source: 'gmail' }),
          transaction({ id: 'p2', merchant: 'Sin candidato', status: 'pending_review', source: 'gmail' }),
        ],
        next_cursor: null,
      })) as never,
      listAccounts: vi.fn(async () => [account({ id: 'acc-1' })]),
      listCategories: vi.fn(async () => []),
      listMatches: vi.fn(async (id: string) => (id === 'p1' ? [other] : [])) as never,
    })
    renderWithApp(<ReviewScreen />, { api })

    expect(await screen.findAllByText(/el mismo movimiento que/)).toHaveLength(1)
    await user.click(screen.getByRole('button', { name: 'Es distinto' }))

    expect(screen.queryByText(/el mismo movimiento que/)).not.toBeInTheDocument()
  })

  it('explains how to continue when there is no account in the currency of the movement', async () => {
    const api = fakeApi({
      listTransactions: vi.fn(async () => ({
        items: [transaction({ id: 'usd1', merchant: 'COMPRA EN DOLARES', currency: 'USD', status: 'pending_review', source: 'gmail', account_id: null })],
        next_cursor: null,
      })) as never,
      listAccounts: vi.fn(async () => [
        account({ id: 'cop', name: 'Tarjeta en pesos', type: 'credit_card' }),
        account({ id: 'exchange', name: 'Exchange', type: 'exchange', currency: 'USD' }),
      ]),
      listCategories: vi.fn(async () => []),
    })
    renderWithApp(<ReviewScreen />, { api })

    expect(await screen.findByText(/No tienes una cuenta en USD/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ir a Cuentas' })).toHaveAttribute('href', '/more/accounts')
    // An exchange account in dollars is not offered as the place a purchase was paid from.
    expect(screen.queryByRole('option', { name: 'Exchange' })).not.toBeInTheDocument()
  })

  it('chooses the category on the card and saves it with the confirmation', async () => {
    const user = userEvent.setup()
    const calls: string[] = []
    const updateTransaction = vi.fn(async () => {
      calls.push('update')
      return transaction({ id: 'c1' })
    })
    const confirmTransaction = vi.fn(async () => {
      calls.push('confirm')
      return transaction({ id: 'c1' })
    })
    const api = fakeApi({
      listTransactions: vi.fn(async () => ({
        items: [transaction({ id: 'c1', merchant: 'Sin categoría aún', status: 'pending_review', source: 'gmail', category_id: null })],
        next_cursor: null,
      })) as never,
      listAccounts: vi.fn(async () => [account({ id: 'acc-1' })]),
      listCategories: vi.fn(async () => [category({ id: 'cat-food', name: 'Mercado' }), category({ id: 'cat-pay', name: 'Sueldo', type: 'income' })]),
      updateTransaction: updateTransaction as never,
      confirmTransaction: confirmTransaction as never,
    })
    renderWithApp(<ReviewScreen />, { api })

    await screen.findByText('Sin categoría aún')
    // Only the categories of the type of the movement are offered.
    expect(screen.queryByRole('option', { name: 'Sueldo' })).not.toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Categoría'), 'cat-food')
    await user.click(screen.getByRole('button', { name: 'Confirmar' }))

    await waitFor(() => expect(confirmTransaction).toHaveBeenCalledWith('c1'))
    expect(updateTransaction).toHaveBeenCalledWith('c1', { category_id: 'cat-food' })
    expect(calls).toEqual(['update', 'confirm'])
  })

  it('confirms without touching the movement when the category was not changed, and does not confirm if saving it fails', async () => {
    const user = userEvent.setup()
    const confirmTransaction = vi.fn(async () => transaction({ id: 'c2' }))
    const updateTransaction = vi.fn(async () => {
      throw new ApiError(422, 'validation_error', 'La categoría no es válida.')
    })
    const api = fakeApi({
      listTransactions: vi.fn(async () => ({
        items: [transaction({ id: 'c2', merchant: 'Con categoría', status: 'pending_review', source: 'gmail', category_id: 'cat-food' })],
        next_cursor: null,
      })) as never,
      listAccounts: vi.fn(async () => [account({ id: 'acc-1' })]),
      listCategories: vi.fn(async () => [category({ id: 'cat-food', name: 'Mercado' }), category({ id: 'cat-gas', name: 'Gasolina' })]),
      updateTransaction: updateTransaction as never,
      confirmTransaction: confirmTransaction as never,
    })
    renderWithApp(<ReviewScreen />, { api })

    await screen.findByText('Con categoría')
    expect(screen.getByLabelText('Categoría')).toHaveValue('cat-food')
    await user.click(screen.getByRole('button', { name: 'Confirmar' }))
    await waitFor(() => expect(confirmTransaction).toHaveBeenCalledWith('c2'))
    expect(updateTransaction).not.toHaveBeenCalled()

    confirmTransaction.mockClear()
    await user.selectOptions(screen.getByLabelText('Categoría'), 'cat-gas')
    await user.click(screen.getByRole('button', { name: 'Confirmar' }))
    expect(await screen.findByText('La categoría no es válida.')).toBeInTheDocument()
    expect(confirmTransaction).not.toHaveBeenCalled()
  })

  it('does not offer a category on a transfer', async () => {
    const api = fakeApi({
      listTransactions: vi.fn(async () => ({
        items: [transaction({ id: 't9', type: 'transfer', status: 'pending_review', source: 'gmail', classification: 'own_transfer', target_account_id: 'acc-2' })],
        next_cursor: null,
      })) as never,
      listAccounts: vi.fn(async () => [account({ id: 'acc-1' }), account({ id: 'acc-2', name: 'Otra' })]),
      listCategories: vi.fn(async () => [category({ id: 'cat-food', name: 'Mercado' })]),
    })
    renderWithApp(<ReviewScreen />, { api })

    await screen.findByRole('button', { name: 'Confirmar' })
    expect(screen.queryByLabelText('Categoría')).not.toBeInTheDocument()
  })
})
