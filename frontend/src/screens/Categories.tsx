import { useState, type FormEvent } from 'react'
import { useCategories, useCreateCategory, useDeleteCategory, useUpdateCategory } from '../api/hooks'
import type { Category, CategoryType } from '../api/types'
import { PageHeader } from '../components/Layout'
import { EmptyState, ErrorState, FormError, ListSkeleton } from '../components/states'
import { useToast } from '../components/Toast'
import { Button, SelectField, TextField } from '../components/ui'
import { CATEGORY_TYPE_LABELS } from '../features/labels'
import { categoryOptions } from '../features/transactions/display'

const TYPES: CategoryType[] = ['expense', 'income', 'transfer']

type Panel = { kind: 'list' } | { kind: 'create' } | { kind: 'edit'; category: Category }

function CategoryForm({
  category,
  defaultType,
  all,
  onDone,
}: {
  category?: Category
  defaultType: CategoryType
  all: Category[]
  onDone: () => void
}) {
  const toast = useToast()
  const create = useCreateCategory()
  const update = useUpdateCategory()
  const remove = useDeleteCategory()
  const [name, setName] = useState(category?.name ?? '')
  const [type, setType] = useState<CategoryType>(category?.type ?? defaultType)
  const [parentId, setParentId] = useState(category?.parent_id ?? '')
  const [nameError, setNameError] = useState<string | undefined>()
  const [deleting, setDeleting] = useState(false)
  const [reassignTo, setReassignTo] = useState('')

  const hasChildren = category ? all.some((c) => c.parent_id === category.id) : false
  // Only two levels exist: a category with children stays on top, and parents are top-level ones.
  const parents = all.filter((c) => c.type === type && c.parent_id === null && c.id !== category?.id)
  const mutation = category ? update : create

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) {
      setNameError('Escribe el nombre de la categoría.')
      return
    }
    setNameError(undefined)
    if (category) {
      const body: { name?: string; parent_id?: string | null } = {}
      if (trimmed !== category.name) body.name = trimmed
      if ((parentId || null) !== category.parent_id) body.parent_id = parentId || null
      if (Object.keys(body).length === 0) return onDone()
      update.mutate(
        { id: category.id, body },
        {
          onSuccess: () => {
            toast.show('Categoría actualizada')
            onDone()
          },
        },
      )
    } else {
      create.mutate(
        { name: trimmed, type, parent_id: parentId || null },
        {
          onSuccess: () => {
            toast.show('Categoría creada')
            onDone()
          },
        },
      )
    }
  }

  const reassignOptions = category ? categoryOptions(all, category.type, category.id) : []

  return (
    <div className="flex flex-col gap-6">
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <TextField label="Nombre" value={name} onChange={(e) => setName(e.target.value)} error={nameError} />
        <SelectField
          label="Tipo"
          value={type}
          disabled={category !== undefined}
          hint={category ? 'El tipo no se puede cambiar.' : undefined}
          onChange={(e) => {
            setType(e.target.value as CategoryType)
            setParentId('')
          }}
        >
          {TYPES.map((t) => (
            <option key={t} value={t}>
              {CATEGORY_TYPE_LABELS[t]}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Categoría principal"
          value={parentId}
          disabled={hasChildren}
          hint={hasChildren ? 'Tiene subcategorías, así que no puede quedar dentro de otra.' : undefined}
          onChange={(e) => setParentId(e.target.value)}
        >
          <option value="">Ninguna (categoría principal)</option>
          {parents.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </SelectField>
        <FormError error={mutation.error} />
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? 'Guardando…' : category ? 'Guardar cambios' : 'Crear categoría'}
        </Button>
      </form>

      {category ? (
        deleting ? (
          <div role="alertdialog" aria-labelledby="del-cat" className="flex flex-col gap-3 rounded-2xl border border-red-300 p-4 dark:border-red-900">
            <p id="del-cat" className="font-medium">
              ¿Eliminar la categoría “{category.name}”?
            </p>
            <SelectField
              label="Pasar sus movimientos a"
              hint="Necesario si la categoría tiene movimientos."
              value={reassignTo}
              onChange={(e) => setReassignTo(e.target.value)}
            >
              <option value="">No reasignar</option>
              {reassignOptions.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </SelectField>
            <FormError error={remove.error} />
            <div className="grid grid-cols-2 gap-2">
              <Button variant="secondary" onClick={() => setDeleting(false)}>
                Cancelar
              </Button>
              <Button
                variant="danger"
                disabled={remove.isPending}
                onClick={() =>
                  remove.mutate(
                    { id: category.id, reassignTo: reassignTo || undefined },
                    {
                      onSuccess: () => {
                        toast.show('Categoría eliminada')
                        onDone()
                      },
                    },
                  )
                }
              >
                {remove.isPending ? 'Eliminando…' : 'Eliminar'}
              </Button>
            </div>
          </div>
        ) : (
          <Button variant="danger" onClick={() => setDeleting(true)}>
            Eliminar categoría
          </Button>
        )
      ) : null}
    </div>
  )
}

export function CategoriesScreen() {
  const categories = useCategories()
  const [panel, setPanel] = useState<Panel>({ kind: 'list' })
  const [type, setType] = useState<CategoryType>('expense')
  const toList = () => setPanel({ kind: 'list' })
  const all = categories.data ?? []

  if (panel.kind !== 'list') {
    return (
      <>
        <PageHeader
          title={panel.kind === 'create' ? 'Nueva categoría' : 'Editar categoría'}
          action={<Button variant="ghost" onClick={toList}>Cancelar</Button>}
        />
        <CategoryForm
          key={panel.kind === 'edit' ? panel.category.id : 'new'}
          category={panel.kind === 'edit' ? panel.category : undefined}
          defaultType={type}
          all={all}
          onDone={toList}
        />
      </>
    )
  }

  const shown = all.filter((c) => c.type === type)
  const parents = shown.filter((c) => c.parent_id === null).sort((a, b) => a.name.localeCompare(b.name, 'es'))

  const row = (c: Category, child: boolean) => (
    <li key={c.id}>
      <button
        type="button"
        onClick={() => setPanel({ kind: 'edit', category: c })}
        className={`flex min-h-11 w-full items-center rounded-xl px-3 text-left text-base active:bg-slate-200 dark:active:bg-slate-800 ${child ? 'pl-8 text-slate-700 dark:text-slate-300' : 'font-medium'}`}
      >
        {c.name}
      </button>
    </li>
  )

  return (
    <>
      <PageHeader
        title="Categorías"
        back={{ to: '/more', label: 'Volver a Más' }}
        action={<Button onClick={() => setPanel({ kind: 'create' })}>Nueva</Button>}
      />
      <div role="group" aria-label="Tipo de categoría" className="mb-4 grid grid-cols-3 gap-2">
        {TYPES.map((t) => (
          <button
            key={t}
            type="button"
            aria-pressed={type === t}
            onClick={() => setType(t)}
            className={`min-h-11 rounded-xl text-sm font-medium ${
              type === t ? 'bg-emerald-500 text-slate-950' : 'bg-slate-200 text-slate-800 dark:bg-slate-800 dark:text-slate-200'
            }`}
          >
            {CATEGORY_TYPE_LABELS[t]}
          </button>
        ))}
      </div>
      {categories.isPending ? (
        <ListSkeleton rows={5} label="Cargando las categorías" />
      ) : categories.isError ? (
        <ErrorState error={categories.error} onRetry={() => void categories.refetch()} />
      ) : parents.length === 0 ? (
        <EmptyState
          title="Sin categorías"
          description={`Aún no hay categorías de ${CATEGORY_TYPE_LABELS[type].toLowerCase()}.`}
          action={<Button onClick={() => setPanel({ kind: 'create' })}>Crear categoría</Button>}
        />
      ) : (
        <ul>
          {parents.flatMap((parent) => [
            row(parent, false),
            ...shown
              .filter((c) => c.parent_id === parent.id)
              .sort((a, b) => a.name.localeCompare(b.name, 'es'))
              .map((c) => row(c, true)),
          ])}
        </ul>
      )}
    </>
  )
}
