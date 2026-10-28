import type { Category } from '../../api/types'
import { categoryLook } from '../appearance'
import type { CategoryOption } from './display'

/** The categories as a grid of icons, with one extra tile to leave the movement without a category. */
export function CategoryPicker({
  options,
  categories,
  value,
  onChange,
  error,
}: {
  options: CategoryOption[]
  categories: Category[]
  value: string
  onChange: (id: string) => void
  error?: string | undefined
}) {
  const byId = new Map(categories.map((category) => [category.id, category]))
  const tiles = [{ id: '', label: 'Sin categoría' }, ...options]

  return (
    <div>
      <p id="category-label" className="mb-2 text-sm font-medium text-slate-300">
        Categoría
      </p>
      <div
        role="radiogroup"
        aria-labelledby="category-label"
        className="grid max-h-72 grid-cols-4 gap-2 overflow-y-auto"
      >
        {tiles.map((tile) => {
          const category = byId.get(tile.id)
          const look = categoryLook(category)
          const selected = tile.id === value
          return (
            <button
              key={tile.id || 'none'}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => onChange(tile.id)}
              className={`flex min-h-[76px] flex-col items-center justify-center gap-1.5 rounded-2xl border px-1 py-2 text-center text-xs leading-[15px] ${
                selected ? 'border-emerald-500 bg-emerald-500/10' : 'border-slate-800 bg-slate-900'
              }`}
            >
              <look.Icon aria-hidden="true" size={24} strokeWidth={1.75} color={category ? look.color : '#a6a6ad'} />
              <span className="line-clamp-2 break-words">{tile.label.trim()}</span>
            </button>
          )
        })}
      </div>
      {error ? (
        <p role="alert" className="mt-1 text-sm text-red-400">
          {error}
        </p>
      ) : null}
    </div>
  )
}
