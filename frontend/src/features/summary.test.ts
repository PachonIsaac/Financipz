import { describe, expect, it } from 'vitest'
import { percentOf, shiftMonth } from './summary'

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
