import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { lazy } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { ApiProvider } from '../api/ApiProvider'
import { fakeApi } from '../test/utils'
import { AppLayout } from './Layout'

function renderLayout(screen_: React.ReactElement) {
  const api = fakeApi({ listTransactions: vi.fn(async () => ({ items: [], next_cursor: null })) as never })
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ApiProvider api={api}>
        <MemoryRouter initialEntries={['/slow']}>
          <Routes>
            <Route element={<AppLayout />}>
              <Route path="slow" element={screen_} />
            </Route>
          </Routes>
        </MemoryRouter>
      </ApiProvider>
    </QueryClientProvider>,
  )
}

describe('the layout while a screen is loading', () => {
  it('keeps the menu and shows the shape of a page, not an empty screen', () => {
    // A screen that never finishes downloading: the old arrangement replaced everything, menu included.
    const Never = lazy(() => new Promise<{ default: () => React.ReactElement }>(() => undefined))

    renderLayout(<Never />)

    expect(screen.getByRole('navigation', { name: 'Navegación principal' })).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Cargando' })).toBeInTheDocument()
  })

  it('keeps the menu when the screen itself fails', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    function Broken(): React.ReactElement {
      throw new Error('boom')
    }

    renderLayout(<Broken />)

    expect(screen.getByRole('navigation', { name: 'Navegación principal' })).toBeInTheDocument()
    expect(screen.getByText(/No se pudo mostrar esta pantalla/)).toBeInTheDocument()
    spy.mockRestore()
  })
})
