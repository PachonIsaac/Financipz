import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { account, category, fakeApi, renderWithApp, transaction } from '../test/utils'
import { MovementDetailScreen } from './MovementDetail'

function setup() {
  const deleteTransaction = vi.fn(async () => undefined)
  const updateTransaction = vi.fn(async () => transaction({ id: 't1' }))
  const api = fakeApi({
    getTransaction: vi.fn(async () =>
      transaction({ id: 't1', merchant: 'Tienda', amount: '45000.00', category_id: 'cat-1' }),
    ),
    listAccounts: vi.fn(async () => [account({ id: 'acc-1', name: 'Cuenta de ahorros' })]),
    listCategories: vi.fn(async () => [category({ id: 'cat-1', name: 'Mercado' })]),
    deleteTransaction,
    updateTransaction,
  })
  renderWithApp(<MovementDetailScreen />, { api, route: '/movements/t1', path: '/movements/:id' })
  return { deleteTransaction, updateTransaction }
}

describe('imported movements', () => {
  function setupImported() {
    const discardTransaction = vi.fn(async () => transaction({ id: 't9', status: 'discarded' }))
    const confirmTransaction = vi.fn(async () => {
      throw new ApiError(409, 'currency_mismatch', 'La moneda de la cuenta no coincide con la del movimiento.')
    })
    const api = fakeApi({
      getTransaction: vi.fn(async () => transaction({ id: 't9', source: 'gmail', status: 'pending_review' })),
      listAccounts: vi.fn(async () => [account({ id: 'acc-1' })]),
      listCategories: vi.fn(async () => []),
      discardTransaction,
      confirmTransaction,
    })
    renderWithApp(<MovementDetailScreen />, { api, route: '/movements/t9', path: '/movements/:id' })
    return { discardTransaction, confirmTransaction }
  }

  it('offers discard instead of delete and confirm for pending ones', async () => {
    const user = userEvent.setup()
    const { discardTransaction } = setupImported()
    expect(await screen.findByRole('button', { name: 'Confirmar' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Eliminar' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Descartar' }))
    await waitFor(() => expect(discardTransaction).toHaveBeenCalledWith('t9'))
  })

  it('shows the API message when confirming fails', async () => {
    const user = userEvent.setup()
    setupImported()
    await user.click(await screen.findByRole('button', { name: 'Confirmar' }))
    expect(await screen.findByText('La moneda de la cuenta no coincide con la del movimiento.')).toBeInTheDocument()
  })
})

describe('movement detail screen', () => {
  it('shows the movement and deletes it only after confirmation', async () => {
    const user = userEvent.setup()
    const { deleteTransaction } = setup()
    expect(await screen.findByText('-$ 45.000,00')).toBeInTheDocument()
    expect(screen.getByText('Mercado')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Eliminar' }))
    expect(deleteTransaction).not.toHaveBeenCalled()
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Eliminar' }))
    await waitFor(() => expect(deleteTransaction).toHaveBeenCalledWith('t1'))
    expect(await screen.findByText('Otra pantalla')).toBeInTheDocument()
    expect(screen.queryByText('Este movimiento ya no existe.')).not.toBeInTheDocument()
  })

  it('sends only the changed fields when editing', async () => {
    const user = userEvent.setup()
    const { updateTransaction } = setup()
    await user.click(await screen.findByRole('button', { name: 'Editar' }))
    const amount = screen.getByLabelText(/^Monto/)
    await user.clear(amount)
    await user.type(amount, '50000')
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    await waitFor(() => expect(updateTransaction).toHaveBeenCalledWith('t1', { amount: '50000.00' }))
  })
})
