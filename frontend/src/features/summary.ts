const DECIMAL = /^-?\d+(\.\d{1,2})?$/

export interface MonthSummary {
  income: string
  expenses: string
  balance: string
}

function pickAmount(data: Record<string, unknown>, names: string[]): string | null {
  for (const name of names) {
    const value = data[name]
    if (typeof value === 'string' && DECIMAL.test(value)) return value
  }
  return null
}

/** Reads the cash-flow totals of the month, or null when the payload does not carry them. */
export function parseSummary(data: Record<string, unknown> | undefined): MonthSummary | null {
  if (!data) return null
  const income = pickAmount(data, ['income', 'total_income'])
  const expenses = pickAmount(data, ['expenses', 'expense', 'total_expenses'])
  const balance = pickAmount(data, ['balance'])
  if (income === null || expenses === null || balance === null) return null
  return { income, expenses, balance }
}

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
