import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
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
