import type { Currency } from '../lib/money'
import { formatMoney, toCents } from '../lib/money'

type Tone = 'auto' | 'neutral'

/** Money in tabular figures. Negative amounts keep the minus sign and turn red; positives can show "+". */
export function Amount({
  value,
  currency,
  exact = false,
  showPlus = false,
  tone = 'auto',
  className = '',
}: {
  value: string
  currency: Currency
  exact?: boolean
  showPlus?: boolean
  tone?: Tone
  className?: string
}) {
  const cents = toCents(value)
  let color = ''
  if (tone === 'auto') {
    if (cents < 0n) color = 'text-rose-600 dark:text-rose-400'
    else if (showPlus && cents > 0n) color = 'text-emerald-700 dark:text-emerald-400'
  }
  return (
    <span className={`tabular whitespace-nowrap ${color} ${className}`}>
      {formatMoney(value, currency, { exact, showPlus })}
    </span>
  )
}
