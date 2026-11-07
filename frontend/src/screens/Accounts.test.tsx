import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { account, fakeApi, renderWithApp } from '../test/utils'
import { AccountsScreen } from './Accounts'

function setup() {
  const updateAccount = vi.fn(async (id: string, body: object) => account({ id, ...body }))
  const api = fakeApi({
    listAccounts: vi.fn(async () => [
      account({ id: 'a1', name: 'Cuenta de ahorros' }),
      account({ id: 'a2', name: 'Ahorro para viaje', type: 'savings', include_in_balance: false }),
    ]),
    listIdentifiers: vi.fn(async () => []),
    updateAccount: updateAccount as never,
  })
  renderWithApp(<AccountsScreen />, { api })
  return { updateAccount }
}

describe('accounts and the balance', () => {
  it('marks the accounts that are left out of the balance in the list', async () => {
    setup()

    expect(await screen.findByText('Fuera del balance')).toBeInTheDocument()
    expect(screen.getAllByText('Fuera del balance')).toHaveLength(1)
  })

  it('turns an account out of the balance with the switch and saves it', async () => {
    const user = userEvent.setup()
    const { updateAccount } = setup()

    await user.click(await screen.findByText('Cuenta de ahorros'))
    const toggle = screen.getByRole('switch', { name: 'Incluir en el balance' })
    expect(toggle).toBeChecked()
    await user.click(toggle)
    expect(toggle).not.toBeChecked()
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))

    expect(updateAccount).toHaveBeenCalledWith('a1', { include_in_balance: false })
  })

  it('shows an excluded account with the switch off', async () => {
    const user = userEvent.setup()
    setup()

    await user.click(await screen.findByText('Ahorro para viaje'))

    expect(screen.getByRole('switch', { name: 'Incluir en el balance' })).not.toBeChecked()
  })

  it('asks for the opening balance only when the account is created, and not when it is edited', async () => {
    const user = userEvent.setup()
    setup()

    await user.click(await screen.findByRole('button', { name: 'Nueva' }))
    expect(screen.getByLabelText('Saldo inicial')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Cancelar' }))

    await user.click(await screen.findByText('Cuenta de ahorros'))
    expect(screen.queryByLabelText('Saldo inicial')).not.toBeInTheDocument()
    expect(screen.queryByText(/Saldo inicial/)).not.toBeInTheDocument()
  })

})

describe('adjusting the balance of an account', () => {
  function adjustSetup() {
    const adjustAccount = vi.fn(async (_id: string, body: object) => ({ transaction: { id: 'x', ...body }, balance: '0.00' }))
    const api = fakeApi({
      listAccounts: vi.fn(async () => [account({ id: 'a1', name: 'Ualá', type: 'wallet', balance: '100000.00' })]),
      listIdentifiers: vi.fn(async () => []),
      adjustAccount: adjustAccount as never,
    })
    renderWithApp(<AccountsScreen />, { api })
    return { adjustAccount }
  }

  async function openAdjust(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByText('Ualá'))
    await user.click(screen.getByRole('button', { name: 'Ajustar saldo' }))
  }

  it('shows the difference as the balance is typed and offers interest only when it is positive', async () => {
    const user = userEvent.setup()
    adjustSetup()
    await openAdjust(user)

    await user.type(screen.getByLabelText(/Saldo real/), '100350')
    expect(screen.getByText(/Diferencia:/)).toHaveTextContent('+$ 350,00')
    expect(screen.getByRole('switch', { name: 'Registrar como intereses' })).toBeInTheDocument()

    await user.clear(screen.getByLabelText(/Saldo real/))
    await user.type(screen.getByLabelText(/Saldo real/), '99000')
    expect(screen.getByText(/Diferencia:/)).toHaveTextContent('-$ 1.000,00')
    expect(screen.queryByRole('switch', { name: 'Registrar como intereses' })).not.toBeInTheDocument()
  })

  it('records the difference as interest, with no reason needed', async () => {
    const user = userEvent.setup()
    const { adjustAccount } = adjustSetup()
    await openAdjust(user)

    await user.type(screen.getByLabelText(/Saldo real/), '100350')
    await user.click(screen.getByRole('switch', { name: 'Registrar como intereses' }))
    await user.click(screen.getByRole('button', { name: 'Registrar intereses' }))

    await waitFor(() => expect(adjustAccount).toHaveBeenCalledWith('a1', { observed_balance: '100350.00', as_interest: true }))
  })

  it('still asks for a reason when it is an ordinary adjustment', async () => {
    const user = userEvent.setup()
    const { adjustAccount } = adjustSetup()
    await openAdjust(user)

    await user.type(screen.getByLabelText(/Saldo real/), '100350')
    await user.click(screen.getByRole('button', { name: 'Ajustar saldo' }))
    expect(await screen.findByText('Escribe el motivo del ajuste.')).toBeInTheDocument()
    expect(adjustAccount).not.toHaveBeenCalled()

    await user.type(screen.getByLabelText('Motivo'), 'Conté el efectivo')
    await user.click(screen.getByRole('button', { name: 'Ajustar saldo' }))
    await waitFor(() => expect(adjustAccount).toHaveBeenCalledWith('a1', { observed_balance: '100350.00', note: 'Conté el efectivo' }))
  })
})
