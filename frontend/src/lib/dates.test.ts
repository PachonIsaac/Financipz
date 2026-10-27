import { describe, expect, it } from 'vitest'
import { dayOf, formatDate, monthStart, toApiDate, todayLocal } from './dates'

describe('dates', () => {
  it('uses Colombian time for today', () => {
    // 03:00 UTC is still the previous evening in Colombia (UTC-5).
    expect(todayLocal(new Date('2026-10-27T03:00:00Z'))).toBe('2026-10-26')
    expect(dayOf('2026-10-27T03:00:00Z')).toBe('2026-10-26')
  })

  it('computes the month start', () => {
    expect(monthStart(new Date('2026-10-26T15:00:00Z'))).toBe('2026-10-01')
  })

  it('keeps the current time for today and uses noon otherwise', () => {
    const now = new Date('2026-10-26T19:32:10Z')
    expect(toApiDate('2026-10-26', now)).toBe('2026-10-26T14:32:10')
    expect(toApiDate('2026-10-20', now)).toBe('2026-10-20T12:00:00')
  })

  it('formats day/month/year', () => {
    expect(formatDate('2026-10-05')).toBe('05/10/2026')
  })
})
