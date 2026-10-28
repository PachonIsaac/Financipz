import { Link } from 'react-router-dom'
import type { Account, Category, Transaction } from '../../api/types'
import { Amount } from '../../components/Amount'
import { Badge } from '../../components/ui'
import { categoryLook, IconChip } from '../appearance'
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
  const account = tx.account_id ? accounts.get(tx.account_id) : undefined
  const target = tx.target_account_id ? accounts.get(tx.target_account_id) : undefined
  const title = tx.merchant || category?.name || TRANSACTION_TYPE_LABELS[tx.type]
  const direction = directionOf(tx.type)
  const look = tx.type === 'transfer' ? categoryLook(undefined, 'transfer') : categoryLook(category)
  const subtitle =
    tx.type === 'transfer'
      ? `${tx.account_id ? (account?.name ?? 'Cuenta') : 'Sin cuenta'} → ${target?.name ?? tx.target_text ?? 'Cuenta'}`
      : [category?.name, tx.account_id ? account?.name : 'Sin cuenta'].filter(Boolean).join(' · ')

  return (
    <li>
      <Link
        to={`/movements/${tx.id}`}
        className="flex min-h-16 items-center gap-3 border-t border-slate-800 py-2 active:bg-slate-800/60 [li:first-child_&]:border-t-0"
      >
        <IconChip icon={look.Icon} color={tx.type === 'transfer' ? undefined : look.color} />
        <div className="min-w-0 flex-1">
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
