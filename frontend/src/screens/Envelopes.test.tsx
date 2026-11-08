import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { Envelope } from '../api/types'
import { account, fakeApi, renderWithApp } from '../test/utils'
import { EnvelopesScreen } from './Envelopes'

function envelope(partial: Partial<Envelope> = {}): Envelope {
  return {
    id: 'e1',
    account_id: 'a1',
    account_name: 'Billetera',
    currency: 'COP',
    name: 'SOAT de la moto',
    target_amount: '480000.00',
    due_date: '2099-02-06',
    repeats_yearly: false,
    balance: '300000.00',
    months_left: 3,
    suggested_monthly: '60000.00',
    ready: false,
    shortfall: '0.00',
    ...partial,
  }
}

function setup(items: Envelope[] = [envelope()], overrides: Parameters<typeof fakeApi>[0] = {}) {
  const api = fakeApi({
    listEnvelopes: vi.fn(async () => ({ envelopes: items, reserved_total: '300000.00', suggested_total: '60000.00' })),
    listAccounts: vi.fn(async () => [account({ id: 'a1', name: 'Billetera', type: 'wallet', balance: '1000000.00', reserved: '300000.00' })]),
    listCategories: vi.fn(async () => []),
    ...overrides,
  })
  renderWithApp(<EnvelopesScreen />, { api })
  return api
}

describe('envelopes', () => {
  it('shows what is set apart, the suggestion of the month and each envelope', async () => {
    setup()

    expect(await screen.findByText('SOAT de la moto')).toBeInTheDocument()
    expect(screen.getByText('Apartado en cajitas')).toBeInTheDocument()
    expect(screen.getByText('Aporte sugerido de este mes')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: /SOAT de la moto/ })).toHaveAttribute('aria-valuenow', '62')
  })

  it('warns when the account holds less than what is set apart', async () => {
    setup([envelope({ shortfall: '40000.00' })])

    expect(await screen.findByRole('alert')).toHaveTextContent('Apartaste más de lo que hay en la cuenta.')
  })

  it('says so when there are no envelopes', async () => {
    setup([])

    expect(await screen.findByText('Aún no tienes cajitas')).toBeInTheDocument()
  })

  it('sets money apart with the suggested amount', async () => {
    const user = userEvent.setup()
    const api = setup(undefined, { envelopeEntry: vi.fn(async () => envelope()) as never })

    await user.click(await screen.findByRole('button', { name: 'Aportar' }))
    await user.click(screen.getByRole('button', { name: /Usar el sugerido/ }))
    await user.click(screen.getByRole('button', { name: 'Aportar' }))

    await waitFor(() => expect(api.envelopeEntry).toHaveBeenCalledWith('e1', { kind: 'contribute', amount: '60000.00' }))
  })

  it('pays with an expense charged to the chosen account', async () => {
    const user = userEvent.setup()
    const pay = vi.fn(async () => ({ envelope: envelope(), transaction_id: 't1', freed: '300000.00' }))
    setup(undefined, { payWithEnvelope: pay as never })

    await user.click(await screen.findByRole('button', { name: 'Pagar' }))
    await user.click(screen.getByRole('button', { name: 'Pagar con la cajita' }))

    await waitFor(() =>
      expect(pay).toHaveBeenCalledWith('e1', {
        expense: { account_id: 'a1', amount: '480000.00', category_id: null, merchant: 'SOAT de la moto' },
      }),
    )
  })

  it('creates an envelope that does not repeat unless it is marked', async () => {
    const user = userEvent.setup()
    const create = vi.fn(async () => envelope())
    setup([], { createEnvelope: create as never })

    await user.click(await screen.findByRole('button', { name: 'Crear cajita' }))
    await user.type(screen.getByLabelText('Nombre'), 'Platzi')
    await user.selectOptions(screen.getByLabelText('Cuenta donde está la plata'), 'a1')
    await user.click(screen.getByRole('button', { name: 'Crear cajita' }))

    await waitFor(() =>
      expect(create).toHaveBeenCalledWith({
        account_id: 'a1',
        name: 'Platzi',
        target_amount: null,
        due_date: null,
        repeats_yearly: false,
      }),
    )
  })
})
