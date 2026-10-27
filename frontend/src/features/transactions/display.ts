import type { Category, CategoryType, Transaction } from '../../api/types'

/** Signed decimal string as the movement affects its own account; transfers are unsigned. */
export function signedAmount(tx: Pick<Transaction, 'type' | 'amount'>): string {
  switch (tx.type) {
    case 'expense':
    case 'adjustment_out':
      return `-${tx.amount}`
    case 'income':
    case 'adjustment_in':
      return tx.amount
    case 'transfer':
      return tx.amount
  }
}

export type Direction = 'in' | 'out' | 'neutral'

export function directionOf(type: Transaction['type']): Direction {
  if (type === 'income' || type === 'adjustment_in') return 'in'
  if (type === 'expense' || type === 'adjustment_out') return 'out'
  return 'neutral'
}

export interface CategoryOption {
  id: string
  label: string
}

/** Main categories followed by their subcategories (indented), optionally for one type. */
export function categoryOptions(categories: Category[], type?: CategoryType, excludeId?: string): CategoryOption[] {
  const matching = categories.filter((c) => (type ? c.type === type : true) && c.id !== excludeId)
  const parents = matching.filter((c) => c.parent_id === null).sort((a, b) => a.name.localeCompare(b.name, 'es'))
  const result: CategoryOption[] = []
  for (const parent of parents) {
    result.push({ id: parent.id, label: parent.name })
    const children = matching
      .filter((c) => c.parent_id === parent.id)
      .sort((a, b) => a.name.localeCompare(b.name, 'es'))
    for (const child of children) {
      result.push({ id: child.id, label: `— ${child.name}` })
    }
  }
  // Orphans (parent not in the filtered set) still need to be selectable.
  const listed = new Set(result.map((r) => r.id))
  for (const category of matching) {
    if (!listed.has(category.id)) result.push({ id: category.id, label: category.name })
  }
  return result
}
