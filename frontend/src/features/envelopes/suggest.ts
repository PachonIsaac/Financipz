import { toCents } from '../../lib/money'

/** Whole calendar months from today to the month of the payment; a payment this month or overdue counts as one. */
export function monthsLeft(today: string, due: string): number {
  const [ty = 0, tm = 0] = today.split('-').map(Number)
  const [dy = 0, dm = 0] = due.split('-').map(Number)
  return Math.max(1, (dy - ty) * 12 + dm - tm)
}

/**
 * What to set apart each month: (target - held) / months left, rounded up to a whole unit, in cents.
 * The server computes the same figure; this one answers while the person types the form.
 */
export function suggestedMonthly(target: string | null, held: string, due: string | null, today: string): bigint | null {
  if (!target || !due) return null
  const missing = toCents(target) - toCents(held)
  if (missing <= 0n) return 0n
  const months = BigInt(monthsLeft(today, due))
  const units = (missing + months * 100n - 1n) / (months * 100n)
  return units * 100n
}
