import { Link } from 'react-router-dom'
import type { Account, Category, Transaction } from '../../api/types'
import { Amount } from '../../components/Amount'
import { Badge } from '../../components/ui'
import { SOURCE_LABELS, STATUS_LABELS, TRANSACTION_TYPE_LABELS } from '../labels'
import { directionOf, signedAmount } from './display'

export function TransactionRow({
  tx,
  accounts,
  categories,
}: {
  tx: Transaction
  accounts: Map<string, Account>
  categories: Map<string, Category>
}) {
  const category = tx.category_id ? categories.get(tx.category_id) : undefined
  const account = accounts.get(tx.account_id)
  const target = tx.target_account_id ? accounts.get(tx.target_account_id) : undefined
  const title = tx.merchant || category?.name || TRANSACTION_TYPE_LABELS[tx.type]
  const direction = directionOf(tx.type)
  const subtitle =
    tx.type === 'transfer'
      ? `${account?.name ?? 'Cuenta'} → ${target?.name ?? tx.target_text ?? 'Cuenta'}`
      : [category?.name, account?.name].filter(Boolean).join(' · ')

  return (
    <li>
      <Link
        to={`/movements/${tx.id}`}
        className="flex min-h-14 items-center justify-between gap-3 rounded-xl px-1 py-2 active:bg-slate-200/60 dark:active:bg-slate-800"
      >
        <div className="min-w-0">
          <p className="truncate text-base font-medium">{title}</p>
          <p className="flex flex-wrap items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400">
            <span className="truncate">{subtitle}</span>
            {tx.source !== 'manual' ? <Badge>{SOURCE_LABELS[tx.source]}</Badge> : null}
            {tx.status !== 'confirmed' ? <Badge tone="warning">{STATUS_LABELS[tx.status]}</Badge> : null}
          </p>
        </div>
        <div className="shrink-0 text-right text-base font-semibold">
          <Amount
            value={signedAmount(tx)}
            currency={tx.currency}
            showPlus={direction === 'in'}
            tone={direction === 'neutral' ? 'neutral' : 'auto'}
          />
          {direction === 'neutral' ? <span className="sr-only"> transferencia</span> : null}
        </div>
      </Link>
    </li>
  )
}
