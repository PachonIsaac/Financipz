import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { Portfolio, Trade } from '../api/types'
import { fakeApi, renderWithApp } from '../test/utils'
import { CryptoScreen } from './Crypto'

const portfolio: Portfolio = {
  snapshot_date: '2026-10-28',
  total_usd: '1798.64',
  total_cop: '5662154.69',
  unpriced_assets: 1,
  // Four decimals, as the API sends it.
  rate: { currency: 'USD', value: '3148.0200', date: '2026-10-28' },
  assets: [
    { asset: 'BTC', quantity: '0.020391590000', value_usd: '1662.54', value_cop: '5233000.00' },
    { asset: 'USDT', quantity: '136.099471450000', value_usd: '136.10', value_cop: '428000.00' },
    { asset: 'XYZ', quantity: '12.000000000000', value_usd: null, value_cop: null },
  ],
}

function trade(id: string, side: 'buy' | 'sell'): Trade {
  return {
    id,
    account_id: 'acc',
    pair: 'BTCUSDT',
    side,
    quantity: '0.001000',
    price: '70000.00000000',
    fee: '0.1',
    fee_asset: 'USDT',
    executed_at: '2026-10-20T15:00:00Z',
    external_id: `BTCUSDT:${id}`,
  }
}

function setup(overrides = {}) {
  const listTrades = vi.fn(async (cursor?: string) =>
    cursor ? { items: [trade('t2', 'sell')], next_cursor: null } : { items: [trade('t1', 'buy')], next_cursor: 'next' },
  )
  const api = fakeApi({
    getPortfolio: vi.fn(async () => portfolio),
    getCryptoHistory: vi.fn(async () => [
      { date: '2026-10-27', total_usd: '1781.98' },
      { date: '2026-10-28', total_usd: '1798.64' },
    ]),
    listTrades: listTrades as never,
    ...overrides,
  })
  renderWithApp(<CryptoScreen />, { api })
  return { listTrades }
}

describe('crypto screen', () => {
  it('shows the portfolio, the assets and what could not be priced', async () => {
    setup()

    expect(await screen.findByLabelText('Valor del portafolio')).toHaveTextContent('US$ 1.798,64')
    expect(screen.getByText(/≈/)).toHaveTextContent('$ 5.662.155')
    expect(screen.getByText(/Instantánea del 28\/10\/2026 · TRM \$ 3\.148/)).toBeInTheDocument()
    expect(screen.getByText('0,02039159 BTC')).toBeInTheDocument()
    expect(screen.getByText('136,09947145 USDT')).toBeInTheDocument()
    expect(screen.getByText('Sin precio')).toBeInTheDocument()
    expect(screen.getByText('1 activo no tiene precio y no está sumado en el total.')).toBeInTheDocument()
  })

  it('draws the history with a table for those who cannot see the chart', async () => {
    setup()

    expect(await screen.findByRole('img', { name: 'Valor del portafolio en dólares por día' })).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Valor del portafolio en dólares por día' })).toBeInTheDocument()
  })

  it('lists trades and loads the next page with the cursor', async () => {
    const { listTrades } = setup()

    expect(await screen.findByText('Compra BTCUSDT')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Cargar más' }))

    expect(await screen.findByText('Venta BTCUSDT')).toBeInTheDocument()
    expect(listTrades).toHaveBeenLastCalledWith('next')
  })

  it('explains what to do when the exchange has never been read', async () => {
    setup({
      getPortfolio: vi.fn(async () => ({ ...portfolio, snapshot_date: null, total_usd: null, total_cop: null, assets: [], unpriced_assets: 0 })),
      getCryptoHistory: vi.fn(async () => []),
      listTrades: vi.fn(async () => ({ items: [], next_cursor: null })),
    })

    expect(await screen.findByText('Aún no hay datos de Binance')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ir a la conexión' })).toBeInTheDocument()
  })
})
