import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { category, fakeApi, renderWithApp } from '../test/utils'
import { CategoriesScreen } from './Categories'

function setup() {
  const createCategory = vi.fn(async (body: object) => category({ id: 'new', ...body } as never))
  const updateCategory = vi.fn(async (id: string, body: object) => category({ id, ...body }))
  const api = fakeApi({
    listCategories: vi.fn(async () => [category({ id: 'c1', name: 'Mercado' })]),
    createCategory: createCategory as never,
    updateCategory: updateCategory as never,
  })
  renderWithApp(<CategoriesScreen />, { api })
  return { createCategory, updateCategory }
}

describe('category appearance', () => {
  it('saves the icon and the color chosen for a new category', async () => {
    const user = userEvent.setup()
    const { createCategory } = setup()

    await user.click(await screen.findByRole('button', { name: 'Nueva' }))
    await user.type(screen.getByLabelText('Nombre'), 'Viajes')
    await user.click(screen.getByRole('radio', { name: 'Azul' }))
    await user.click(screen.getByRole('radio', { name: 'Viaje' }))
    await user.click(screen.getByRole('button', { name: 'Crear categoría' }))

    expect(createCategory).toHaveBeenCalledWith({
      name: 'Viajes',
      type: 'expense',
      parent_id: null,
      icon: 'plane',
      color: '#5b9ef0',
    })
  })

  it('sends only what changed when editing, and starts with nothing chosen when none is stored', async () => {
    const user = userEvent.setup()
    const { updateCategory } = setup()

    await user.click(await screen.findByText('Mercado'))
    expect(screen.getByRole('radio', { name: 'Naranja' })).toHaveAttribute('aria-checked', 'false')
    await user.click(screen.getByRole('radio', { name: 'Rosa' }))
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))

    expect(updateCategory).toHaveBeenCalledWith('c1', { color: '#e879a6' })
  })
})
