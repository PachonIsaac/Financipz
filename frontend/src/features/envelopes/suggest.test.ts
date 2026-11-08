import { describe, expect, it } from 'vitest'
import { monthsLeft, suggestedMonthly } from './suggest'

describe('suggested monthly contribution', () => {
  it('counts the calendar months to the payment month', () => {
    expect(monthsLeft('2026-11-07', '2027-02-06')).toBe(3)
    expect(monthsLeft('2026-11-07', '2026-11-30')).toBe(1)
    expect(monthsLeft('2026-11-07', '2026-01-01')).toBe(1)
  })

  it('divides what is missing and rounds up to a whole peso', () => {
    expect(suggestedMonthly('480000.00', '300000.00', '2027-02-06', '2026-11-07')).toBe(6_000_000n)
    expect(suggestedMonthly('100.00', '0.00', '2027-02-06', '2026-11-07')).toBe(3_400n)
  })

  it('is zero when the target is reached and absent without target or date', () => {
    expect(suggestedMonthly('100.00', '150.00', '2027-02-06', '2026-11-07')).toBe(0n)
    expect(suggestedMonthly(null, '0.00', '2027-02-06', '2026-11-07')).toBeNull()
    expect(suggestedMonthly('100.00', '0.00', null, '2026-11-07')).toBeNull()
  })
})
