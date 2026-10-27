import { toCents } from '../lib/money'

/** YYYY-MM shifted by `delta` months. */
export function shiftMonth(month: string, delta: number): string {
  const [yearText = '0', monthText = '1'] = month.split('-')
  const index = Number(yearText) * 12 + (Number(monthText) - 1) + delta
  const year = Math.floor(index / 12)
  const next = (index % 12) + 1
  return `${year}-${String(next).padStart(2, '0')}`
}

const monthFormatter = new Intl.DateTimeFormat('es-CO', { timeZone: 'UTC', month: 'long', year: 'numeric' })

export function formatMonth(month: string): string {
  return monthFormatter.format(new Date(`${month}-01T00:00:00Z`))
}

/** Short month name ("oct.") for a YYYY-MM value. */
export function shortMonth(month: string): string {
  return new Intl.DateTimeFormat('es-CO', { timeZone: 'UTC', month: 'short' }).format(new Date(`${month}-01T00:00:00Z`))
}

/** Whole percentage (0-100) of `amount` relative to `max`, using integer math. */
export function percentOf(amount: string, max: string): number {
  const total = toCents(max)
  const part = toCents(amount)
  if (total <= 0n || part <= 0n) return 0
  return Math.min(100, Number((part * 100n) / total))
}
