import { describe, expect, it } from 'vitest'
import { percentOf, shiftMonth, topCategories } from './summary'

describe('summary helpers', () => {
  it('shifts months across years', () => {
    expect(shiftMonth('2026-01', -1)).toBe('2025-12')
    expect(shiftMonth('2026-12', 1)).toBe('2027-01')
  })

  it('computes percentages with integer math', () => {
    expect(percentOf('250.00', '1000.00')).toBe(25)
    expect(percentOf('1000.00', '0.00')).toBe(0)
    expect(percentOf('-5.00', '10.00')).toBe(0)
    expect(percentOf('2000.00', '1000.00')).toBe(100)
  })
})

describe('topCategories', () => {
  const item = (name: string, amount: string, id: string | null = name) => ({ category_id: id, name, color: null, amount })

  it('keeps everything when there are few categories, biggest first', () => {
    const result = topCategories([item('A', '10.00'), item('B', '30.00'), item('C', '20.00')])

    expect(result.map((entry) => entry.name)).toEqual(['B', 'C', 'A'])
  })

  it('gathers the smallest ones into a single entry with their total', () => {
    const result = topCategories([item('A', '50.00'), item('B', '40.00'), item('C', '30.00'), item('D', '5.50'), item('E', '4.50')], 3)

    expect(result.map((entry) => entry.name)).toEqual(['A', 'B', 'C', 'Otras (2)'])
    expect(result[3]).toMatchObject({ amount: '10.00', others: true })
  })
})
