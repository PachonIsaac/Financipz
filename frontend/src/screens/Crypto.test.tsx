import { fireEvent, screen, waitFor } from '@testing-library/react'
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

const HISTORY = [
  {
    date: '2026-10-26',
    total_usd: '1700.00',
    assets: [
      { asset: 'BTC', quantity: '0.019000000000', value_usd: '1560.00' },
      { asset: 'USDT', quantity: '140.000000000000', value_usd: '140.00' },
      { asset: 'OLD', quantity: '5.000000000000', value_usd: '0.00' },
    ],
  },
  {
    date: '2026-10-27',
    total_usd: '1781.98',
    assets: [
      { asset: 'BTC', quantity: '0.020000000000', value_usd: '1645.00' },
      { asset: 'USDT', quantity: '136.980000000000', value_usd: '136.98' },
    ],
  },
  {
    date: '2026-10-28',
    total_usd: '1798.64',
    assets: [
      { asset: 'BTC', quantity: '0.020391590000', value_usd: '1662.54' },
      { asset: 'USDT', quantity: '136.100000000000', value_usd: '136.10' },
    ],
  },
]

function setup(overrides = {}) {
  const listTrades = vi.fn(async (cursor?: string) =>
    cursor ? { items: [trade('t2', 'sell')], next_cursor: null } : { items: [trade('t1', 'buy')], next_cursor: 'next' },
  )
  const api = fakeApi({
    getPortfolio: vi.fn(async () => portfolio),
    getCryptoHistory: vi.fn(async () => HISTORY),
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
    expect(screen.getAllByText('0,02039159 BTC').length).toBeGreaterThan(0)
    expect(screen.getByText('136,09947145 USDT')).toBeInTheDocument()
    expect(screen.getByText('Sin precio')).toBeInTheDocument()
    expect(screen.getByText('1 activo no tiene precio y no está sumado en el total.')).toBeInTheDocument()
  })

  it('draws the history with a table for those who cannot see the chart', async () => {
    setup()

    expect(await screen.findByRole('slider', { name: 'Valor del portafolio en dólares por día' })).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Valor del portafolio en dólares por día' })).toBeInTheDocument()
  })

  it('starts on the last day, with its exact balances and nothing to compare', async () => {
    setup()

    const chart = await screen.findByRole('slider', { name: 'Valor del portafolio en dólares por día' })

    expect(chart).toHaveAttribute('aria-valuenow', '2')
    const detail = screen.getByText('Último día sincronizado').parentElement!
    expect(detail).toHaveTextContent('28/10/2026')
    expect(detail).toHaveTextContent('US$ 1.798,64')
    expect(detail).toHaveTextContent('0,02039159 BTC')
    expect(screen.queryByText(/Hasta hoy/)).not.toBeInTheDocument()
  })

  it('shows another day with its balances and how they changed until today, using the arrow keys', async () => {
    const user = userEvent.setup()
    setup()
    const chart = await screen.findByRole('slider', { name: 'Valor del portafolio en dólares por día' })

    chart.focus()
    await user.keyboard('{ArrowLeft}{ArrowLeft}')

    expect(chart).toHaveAttribute('aria-valuenow', '0')
    const detail = screen.getByText(/Hasta hoy/).parentElement!
    expect(detail).toHaveTextContent('26/10/2026')
    expect(detail).toHaveTextContent('US$ 1.700,00')
    // 1.798,64 - 1.700,00 = +98,64, which is 5,8 % of that day.
    expect(screen.getByText(/Hasta hoy/)).toHaveTextContent('+US$ 98,64 (+5,8 %)')
    expect(detail).toHaveTextContent('0,019 BTC')
    expect(detail).toHaveTextContent('+0,00139159 BTC · +US$ 102,54')
    expect(detail).toHaveTextContent('−3,9 USDT · −US$ 3,90')
    expect(detail).toHaveTextContent('ya no lo tienes')
  })

  it('chooses the day nearest to where the chart is touched', async () => {
    setup()
    const chart = await screen.findByRole('slider', { name: 'Valor del portafolio en dólares por día' })
    vi.spyOn(chart, 'getBoundingClientRect').mockReturnValue({ left: 0, width: 330, top: 0, right: 330, bottom: 100, height: 100, x: 0, y: 0, toJSON: () => ({}) })

    fireEvent.pointerDown(chart, { clientX: 6, pointerId: 1, pointerType: 'touch' })
    expect(chart).toHaveAttribute('aria-valuenow', '0')

    fireEvent.pointerMove(chart, { clientX: 170, pointerId: 1, pointerType: 'mouse' })
    expect(chart).toHaveAttribute('aria-valuenow', '1')
    expect(screen.getByText(/Hasta hoy/).parentElement).toHaveTextContent('27/10/2026')

    fireEvent.pointerMove(chart, { clientX: 400, pointerId: 1, pointerType: 'mouse' })
    expect(chart).toHaveAttribute('aria-valuenow', '2')
  })

  it('shows the last five trades and all of them after asking for more', async () => {
    const many = Array.from({ length: 7 }, (_, index) => trade(`t${index}`, index % 2 === 0 ? 'buy' : 'sell'))
    const listTrades = vi.fn(async (cursor?: string) =>
      cursor ? { items: many.slice(5), next_cursor: null } : { items: many.slice(0, 5), next_cursor: 'next' },
    )
    setup({ listTrades: listTrades as never })

    expect((await screen.findAllByText(/^(Compra|Venta) BTCUSDT$/)).length).toBe(5)
    await userEvent.click(screen.getByRole('button', { name: 'Ver más' }))

    await waitFor(() => expect(screen.getAllByText(/^(Compra|Venta) BTCUSDT$/).length).toBe(7))
    expect(listTrades).toHaveBeenLastCalledWith('next')
    await userEvent.click(await screen.findByRole('button', { name: 'Ver menos' }))
    expect(screen.getAllByText(/^(Compra|Venta) BTCUSDT$/).length).toBe(5)
  })

  it('offers no "Ver más" when there are no more than five trades', async () => {
    setup({ listTrades: vi.fn(async () => ({ items: [trade('t1', 'buy')], next_cursor: null })) as never })

    expect(await screen.findByText('Compra BTCUSDT')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ver más' })).not.toBeInTheDocument()
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
