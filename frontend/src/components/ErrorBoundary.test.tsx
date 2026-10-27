import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { ErrorBoundary, RouteErrorBoundary } from './ErrorBoundary'

function Boom({ explode }: { explode: boolean }) {
  if (explode) throw new Error('boom')
  return <p>Todo bien</p>
}

describe('ErrorBoundary', () => {
  it('shows a friendly message instead of a blank page, and lets the user retry', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    let explode = true
    const { rerender } = render(
      <ErrorBoundary label="No se pudo mostrar esto.">
        <Boom explode={explode} />
      </ErrorBoundary>,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('No se pudo mostrar esto.')

    explode = false
    rerender(
      <ErrorBoundary label="No se pudo mostrar esto.">
        <Boom explode={explode} />
      </ErrorBoundary>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))

    expect(screen.getByText('Todo bien')).toBeInTheDocument()
    spy.mockRestore()
  })

  it('leaves the rest of the page alone', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <>
        <p>Menú</p>
        <ErrorBoundary>
          <Boom explode />
        </ErrorBoundary>
      </>,
    )

    expect(screen.getByText('Menú')).toBeInTheDocument()
    spy.mockRestore()
  })
})

describe('RouteErrorBoundary', () => {
  it('recovers when the user moves to another screen', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    function Broken() {
      const go = useNavigate()
      return (
        <>
          <button onClick={() => go('/fine')}>ir</button>
          <Boom explode />
        </>
      )
    }
    function Nav() {
      const go = useNavigate()
      return <button onClick={() => go('/fine')}>ir a otra</button>
    }
    render(
      <MemoryRouter initialEntries={['/broken']}>
        <Nav />
        <RouteErrorBoundary>
          <Routes>
            <Route path="/broken" element={<Broken />} />
            <Route path="/fine" element={<p>Pantalla sana</p>} />
          </Routes>
        </RouteErrorBoundary>
      </MemoryRouter>,
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()

    fireEvent.click(screen.getByText('ir a otra'))

    expect(screen.getByText('Pantalla sana')).toBeInTheDocument()
    spy.mockRestore()
  })
})
