import type { HistoryPoint } from '../../api/types'
import { fromCents, toCents } from '../../lib/money'

// Quantities carry up to twelve decimals, so they are compared as whole numbers of the smallest unit.
const QUANTITY_DECIMALS = 12
const SCALE = 10n ** BigInt(QUANTITY_DECIMALS)

function toUnits(quantity: string): bigint {
  const negative = quantity.startsWith('-')
  const [whole = '0', fraction = ''] = quantity.replace('-', '').split('.')
  const units = BigInt(whole || '0') * SCALE + BigInt(fraction.padEnd(QUANTITY_DECIMALS, '0').slice(0, QUANTITY_DECIMALS))
  return negative ? -units : units
}

function fromUnits(units: bigint): string {
  const negative = units < 0n
  const abs = negative ? -units : units
  const text = `${abs / SCALE}.${(abs % SCALE).toString().padStart(QUANTITY_DECIMALS, '0')}`
  return negative ? `-${text}` : text
}

export type AssetStatus = 'same' | 'changed' | 'new' | 'gone' | 'unpriced'

export interface AssetChange {
  asset: string
  status: AssetStatus
  /** What was held that day and what is held now; `null` when the asset was not held then. */
  then: string | null
  now: string | null
  /** Change in quantity since that day (signed decimal), and in dollars when both days have a price. */
  quantityChange: string
  valueChange: string | null
}

export interface Comparison {
  /** Change of the total in dollars since that day (signed decimal), and as a percentage with one decimal. */
  totalChange: string
  percent: string | null
  assets: AssetChange[]
}

/** How the portfolio changed from `then` until `now`: the total, and each asset. Nothing is invented without a price. */
export function compareDays(then: HistoryPoint, now: HistoryPoint): Comparison {
  const totalThen = toCents(then.total_usd)
  const change = toCents(now.total_usd) - totalThen
  // Tenths of a percent, rounded toward zero, kept as whole numbers.
  const tenths = totalThen === 0n ? null : (change * 1000n) / totalThen
  const percent =
    tenths === null ? null : `${tenths < 0n ? '-' : ''}${(tenths < 0n ? -tenths : tenths) / 10n}.${(tenths < 0n ? -tenths : tenths) % 10n}`

  const before = new Map(then.assets.map((item) => [item.asset, item]))
  const after = new Map(now.assets.map((item) => [item.asset, item]))
  const names = [...now.assets.map((item) => item.asset), ...then.assets.filter((item) => !after.has(item.asset)).map((item) => item.asset)]

  const assets = names.map((asset): AssetChange => {
    const past = before.get(asset)
    const present = after.get(asset)
    const quantityChange = fromUnits(toUnits(present?.quantity ?? '0') - toUnits(past?.quantity ?? '0'))
    const priced = past?.value_usd != null && present?.value_usd != null
    const valueChange = priced ? fromCents(toCents(present.value_usd!) - toCents(past.value_usd!)) : null
    let status: AssetStatus
    if (!past) status = 'new'
    else if (!present) status = 'gone'
    else if (!priced) status = 'unpriced'
    else status = toUnits(quantityChange) === 0n && toCents(valueChange!) === 0n ? 'same' : 'changed'
    return { asset, status, then: past?.quantity ?? null, now: present?.quantity ?? null, quantityChange, valueChange }
  })
  return { totalChange: fromCents(change), percent, assets }
}

/** -1, 0 or 1 for a signed decimal string, whatever its number of decimals. */
export function signOf(value: string): -1 | 0 | 1 {
  if (value.startsWith('-')) return /[1-9]/.test(value) ? -1 : 0
  return /[1-9]/.test(value) ? 1 : 0
}
