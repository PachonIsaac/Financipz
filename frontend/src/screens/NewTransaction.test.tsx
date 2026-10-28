import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { account, category, fakeApi, renderWithApp, transaction } from '../test/utils'
import { NewTransactionScreen } from './NewTransaction'

const accounts = [
  account({ id: 'acc-1', name: 'Cuenta de ahorros' }),
  account({ id: 'acc-2', name: 'Efectivo', type: 'cash' }),
  account({ id: 'acc-usd', name: 'Cuenta en dólares', currency: 'USD' }),
]
const categories = [category({ id: 'cat-1', name: 'Mercado' }), category({ id: 'cat-2', name: 'Sueldo', type: 'income' })]

function setup() {
  const createTransaction = vi.fn(async () => transaction({ id: 'new' }))
  const api = fakeApi({
    listAccounts: vi.fn(async () => accounts),
    listCategories: vi.fn(async () => categories),
    createTransaction,
  })
  renderWithApp(<NewTransactionScreen />, { api, route: '/new', path: '/new' })
  return { createTransaction }
}

describe('quick add screen', () => {
  it('saves an expense with a decimal-string amount', async () => {
    const user = userEvent.setup()
    const { createTransaction } = setup()

    const amount = await screen.findByLabelText(/^Monto/)
    await user.type(amount, '45.000')
    await user.click(screen.getByRole('radio', { name: 'Mercado' }))
    await user.type(screen.getByLabelText('Comercio (opcional)'), 'Tienda')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))

    await waitFor(() => expect(createTransaction).toHaveBeenCalledOnce())
    expect(createTransaction).toHaveBeenCalledWith(
      expect.objectContaining({
        account_id: 'acc-1',
        type: 'expense',
        amount: '45000.00',
        category_id: 'cat-1',
        merchant: 'Tienda',
      }),
    )
    expect(await screen.findByText('Otra pantalla')).toBeInTheDocument()
  })

  it('shows validation errors and does not call the API', async () => {
    const user = userEvent.setup()
    const { createTransaction } = setup()
    await screen.findByLabelText(/^Monto/)
    await user.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByText('Escribe el monto.')).toBeInTheDocument()
    expect(createTransaction).not.toHaveBeenCalled()
  })

  it('asks for the destination and the received amount between currencies', async () => {
    const user = userEvent.setup()
    const { createTransaction } = setup()
    await screen.findByLabelText(/^Monto/)
    await user.click(screen.getByRole('button', { name: 'Transferencia' }))
    await user.type(screen.getByLabelText(/^Monto/), '400000')
    await user.selectOptions(screen.getByLabelText('Cuenta destino'), 'acc-usd')
    await user.type(screen.getByLabelText(/Monto recibido/), '100,50')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))

    await waitFor(() => expect(createTransaction).toHaveBeenCalledOnce())
    expect(createTransaction).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'transfer',
        amount: '400000.00',
        target_account_id: 'acc-usd',
        target_amount: '100.50',
      }),
    )
  })

  it('shows the backend message when saving fails', async () => {
    const user = userEvent.setup()
    const { ApiError } = await import('../api/client')
    const api = fakeApi({
      listAccounts: vi.fn(async () => accounts),
      listCategories: vi.fn(async () => categories),
      createTransaction: vi.fn(async () => {
        throw new ApiError(409, 'conflict', 'No se pudo guardar el movimiento.')
      }),
    })
    renderWithApp(<NewTransactionScreen />, { api, route: '/new', path: '/new' })
    await user.type(await screen.findByLabelText(/^Monto/), '1000')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByText('No se pudo guardar el movimiento.')).toBeInTheDocument()
  })
})
