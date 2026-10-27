// Money helpers. Amounts travel as decimal strings ("1250000.00") and are handled as integer
// cents (bigint) so no floating point is ever involved.

export type Currency = 'COP' | 'USD'

const AMOUNT_PATTERN = /^-?\d+(\.\d{1,2})?$/

/** Converts a canonical decimal string ("-12.5") to integer cents. Throws on malformed input. */
export function toCents(value: string): bigint {
  const text = value.trim()
  if (!AMOUNT_PATTERN.test(text)) {
    throw new Error(`Invalid amount: ${value}`)
  }
  const negative = text.startsWith('-')
  const unsigned = negative ? text.slice(1) : text
  const [whole = '0', fraction = ''] = unsigned.split('.')
  const cents = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'))
  return negative ? -cents : cents
}

/** Converts integer cents to a canonical decimal string with two decimals. */
export function fromCents(cents: bigint): string {
  const negative = cents < 0n
  const abs = negative ? -cents : cents
  const whole = abs / 100n
  const fraction = (abs % 100n).toString().padStart(2, '0')
  return `${negative && abs !== 0n ? '-' : ''}${whole}.${fraction}`
}

const RATE_PATTERN = /^\d+(\.\d{1,4})?$/

/**
 * Formats an exchange rate for display. Rates travel with up to four decimals ("3157.9400"), which
 * money amounts never have, so they cannot go through `toCents`. The result is rounded to cents,
 * half up, and shown like an amount: "$ 3.157,94".
 */
export function formatRate(value: string): string {
  const text = value.trim()
  if (!RATE_PATTERN.test(text)) {
    throw new Error(`Invalid rate: ${value}`)
  }
  const [whole = '0', fraction = ''] = text.split('.')
  const tenThousandths = BigInt(whole) * 10000n + BigInt(fraction.padEnd(4, '0'))
  const cents = (tenThousandths + 50n) / 100n
  return formatMoney(fromCents(cents), 'COP', { exact: true })
}

export function sumCents(values: string[]): bigint {
  return values.reduce((total, value) => total + toCents(value), 0n)
}

export function isPositive(value: string): boolean {
  return toCents(value) > 0n
}

function groupThousands(digits: string): string {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, '.')
}

/** Rounds cents to whole units, half away from zero. */
function roundToUnits(cents: bigint): bigint {
  const negative = cents < 0n
  const abs = negative ? -cents : cents
  const units = (abs + 50n) / 100n
  return negative ? -units : units
}

export interface FormatOptions {
  /** Force two decimals even for COP (detail views). */
  exact?: boolean
  /** Prefix positive amounts with "+". */
  showPlus?: boolean
}

/**
 * Formats an amount for es-CO: "." for thousands and "," for decimals.
 * COP shows no decimals unless `exact`; USD always shows two. Negatives lead with "-".
 */
export function formatMoney(value: string, currency: Currency, options: FormatOptions = {}): string {
  const cents = toCents(value)
  const negative = cents < 0n
  const symbol = currency === 'USD' ? 'US$' : '$'
  const withDecimals = currency === 'USD' || options.exact === true
  let body: string
  let isZero: boolean
  if (withDecimals) {
    const abs = negative ? -cents : cents
    body = `${groupThousands((abs / 100n).toString())},${(abs % 100n).toString().padStart(2, '0')}`
    isZero = abs === 0n
  } else {
    const units = roundToUnits(cents)
    const abs = units < 0n ? -units : units
    body = groupThousands(abs.toString())
    isZero = abs === 0n
  }
  const sign = negative && !isZero ? '-' : options.showPlus && !isZero && !negative ? '+' : ''
  return `${sign}${symbol} ${body}`
}

/**
 * Normalizes what the user types into a canonical decimal string, or returns null if it is not
 * a valid amount. A comma is the decimal separator and dots group thousands; a lone dot followed
 * by one or two digits is also read as a decimal point ("12.50").
 */
export function parseAmountInput(input: string, options: { allowNegative?: boolean } = {}): string | null {
  let text = input.replace(/[\s$]|US/g, '')
  let negative = false
  if (text.startsWith('-')) {
    if (!options.allowNegative) return null
    negative = true
    text = text.slice(1)
  }
  if (text === '') return null

  const GROUPED = /^\d{1,3}(\.\d{3})+$/
  let whole: string
  let fraction = ''
  if (text.includes(',')) {
    const parts = text.split(',')
    if (parts.length !== 2) return null
    const rawWhole = parts[0] ?? ''
    if (rawWhole !== '' && !/^\d+$/.test(rawWhole) && !GROUPED.test(rawWhole)) return null
    whole = rawWhole.replace(/\./g, '')
    fraction = parts[1] ?? ''
  } else if (/^\d+\.\d{1,2}$/.test(text)) {
    const [w = '', f = ''] = text.split('.')
    whole = w
    fraction = f
  } else if (/^\d+$/.test(text) || GROUPED.test(text)) {
    whole = text.replace(/\./g, '')
  } else {
    return null
  }
  if (whole === '') whole = '0'
  if (!/^\d+$/.test(whole) || !/^\d{0,2}$/.test(fraction)) return null
  if (whole.replace(/^0+(?=\d)/, '').length > 12) return null
  const normalized = `${whole.replace(/^0+(?=\d)/, '')}.${fraction.padEnd(2, '0')}`
  if (negative && toCents(normalized) !== 0n) return `-${normalized}`
  return normalized
}
