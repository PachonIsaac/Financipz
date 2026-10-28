import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import type { Integration } from '../api/types'
import { fakeApi, renderWithApp } from '../test/utils'
import { BinanceScreen } from './Binance'

const connected: Integration = {
  provider: 'binance',
  status: 'active',
  last_synced_at: '2026-10-28T19:59:00Z',
  warnings: [{ code: 'ip_not_restricted', message: 'La clave no tiene restricción de IP.' }],
}

function setup(integration: Integration | null, overrides = {}) {
  const api = fakeApi({
    listIntegrations: vi.fn(async () => (integration ? [integration] : [])),
    ...overrides,
  })
  renderWithApp(<BinanceScreen />, { api })
  return api
}

describe('binance connection', () => {
  it('shows a connected key with its warnings and the actions', async () => {
    setup(connected)

    expect(await screen.findByText('Conectada')).toBeInTheDocument()
    expect(screen.getByText('La clave no tiene restricción de IP.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sincronizar' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Secreto')).not.toBeInTheDocument()
  })

  it('reads the exchange and says what is new', async () => {
    const syncBinance = vi.fn(async () => ({
      snapshot_date: '2026-10-28',
      assets: 2,
      unpriced_assets: 0,
      total_usd: '1798.64',
      new_trades: 3,
      trades_complete: true,
      warnings: [],
      last_synced_at: '2026-10-28T20:00:00Z',
    }))
    setup(connected, { syncBinance })

    await userEvent.click(await screen.findByRole('button', { name: 'Sincronizar' }))

    expect(await screen.findByText('Sincronizado: 3 operaciones nuevas')).toBeInTheDocument()
  })

  it('shows why a read failed', async () => {
    const syncBinance = vi.fn(async () => {
      throw new ApiError(502, 'binance_region_blocked', 'Binance no atiende consultas desde la ubicación del servidor.')
    })
    setup(connected, { syncBinance })

    await userEvent.click(await screen.findByRole('button', { name: 'Sincronizar' }))

    expect(await screen.findByText(/no atiende consultas desde la ubicación/)).toBeInTheDocument()
  })

  it('asks before disconnecting', async () => {
    const disconnectBinance = vi.fn(async () => undefined)
    setup(connected, { disconnectBinance })

    await userEvent.click(await screen.findByRole('button', { name: 'Desconectar' }))
    expect(disconnectBinance).not.toHaveBeenCalled()
    await userEvent.click(within_dialog('Desconectar'))

    await waitFor(() => expect(disconnectBinance).toHaveBeenCalled())
  })

  it('connects a key, trimmed, from the form when nothing is connected', async () => {
    const connectBinance = vi.fn(async () => connected)
    setup(null, { connectBinance })

    await userEvent.type(await screen.findByLabelText('Clave de API'), '  clave-123  ')
    await userEvent.type(screen.getByLabelText('Secreto'), 'secreto-456')
    await userEvent.click(screen.getByRole('button', { name: 'Conectar' }))

    expect(connectBinance).toHaveBeenCalledWith('clave-123', 'secreto-456')
  })

  it('does not call the API when a field is empty', async () => {
    const connectBinance = vi.fn(async () => connected)
    setup(null, { connectBinance })

    await userEvent.click(await screen.findByRole('button', { name: 'Conectar' }))

    expect(await screen.findByText('Escribe la clave de API y el secreto.')).toBeInTheDocument()
    expect(connectBinance).not.toHaveBeenCalled()
  })
})

/** The confirmation button inside the dialog, not the one that opened it. */
function within_dialog(name: string): HTMLElement {
  const dialog = screen.getByRole('alertdialog')
  const button = [...dialog.querySelectorAll('button')].find((item) => item.textContent?.includes(name))
  if (!button) throw new Error(`No "${name}" button in the dialog`)
  return button
}
