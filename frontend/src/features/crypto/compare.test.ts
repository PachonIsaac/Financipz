import { describe, expect, it } from 'vitest'
import type { HistoryPoint } from '../../api/types'
import { compareDays } from './compare'

const day = (date: string, total: string, assets: [string, string, string | null][]): HistoryPoint => ({
  date,
  total_usd: total,
  assets: assets.map(([asset, quantity, value_usd]) => ({ asset, quantity, value_usd })),
})

describe('compareDays', () => {
  it('gives the change of the total, in dollars and as a percentage', () => {
    const result = compareDays(day('2026-10-20', '1000.00', []), day('2026-10-28', '1034.50', []))

    expect(result.totalChange).toBe('34.50')
    expect(result.percent).toBe('3.4')
  })

  it('keeps the sign of a fall and does not divide by a total of zero', () => {
    expect(compareDays(day('a', '200.00', []), day('b', '150.00', []))).toMatchObject({ totalChange: '-50.00', percent: '-25.0' })
    expect(compareDays(day('a', '0.00', []), day('b', '150.00', [])).percent).toBeNull()
  })

  it('compares each asset by quantity and by value, exactly', () => {
    const then = day('a', '300.00', [['BTC', '0.001200000000', '100.00'], ['USDT', '200.000000000000', '200.00']])
    const now = day('b', '350.30', [['BTC', '0.001000000000', '150.30'], ['USDT', '200.000000000000', '200.00']])

    const [btc, usdt] = compareDays(then, now).assets

    expect(btc).toMatchObject({ asset: 'BTC', status: 'changed', quantityChange: '-0.000200000000', valueChange: '50.30' })
    expect(usdt).toMatchObject({ asset: 'USDT', status: 'same', quantityChange: '0.000000000000', valueChange: '0.00' })
  })

  it('marks an asset that was not held then as new, and one that is not held now as gone', () => {
    const then = day('a', '10.00', [['OLD', '5', '10.00']])
    const now = day('b', '20.00', [['NEW', '2.5', '20.00']])

    const result = compareDays(then, now).assets

    expect(result.map((item) => [item.asset, item.status])).toEqual([['NEW', 'new'], ['OLD', 'gone']])
    expect(result[0]).toMatchObject({ then: null, now: '2.5', quantityChange: '2.500000000000', valueChange: null })
    expect(result[1]).toMatchObject({ then: '5', now: null, quantityChange: '-5.000000000000', valueChange: null })
  })

  it('does not invent a change of value when one of the days has no price', () => {
    const then = day('a', '0.00', [['OBSCURE', '3', null]])
    const now = day('b', '0.00', [['OBSCURE', '4', null]])

    expect(compareDays(then, now).assets[0]).toMatchObject({ status: 'unpriced', quantityChange: '1.000000000000', valueChange: null })
  })
})
