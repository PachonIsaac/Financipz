import { screen } from '@testing-library/react'
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
})
