import { QueryClient } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

type AuthListener = (event: string, session: { access_token: string; user: { email: string } } | null) => void

const session = { access_token: 'token-abc', user: { email: 'persona@example.com' } }
const auth = vi.hoisted(() => ({
  listener: null as unknown,
  getSession: vi.fn(),
  signOut: vi.fn(),
  signInWithPassword: vi.fn(),
}))

vi.mock('@supabase/supabase-js', () => ({
  createClient: () => ({
    auth: {
      getSession: auth.getSession,
      signOut: auth.signOut,
      signInWithPassword: auth.signInWithPassword,
      onAuthStateChange: (callback: unknown) => {
        auth.listener = callback
        return { data: { subscription: { unsubscribe: vi.fn() } } }
      },
    },
  }),
}))

vi.mock('./lib/config', () => ({
  config: { apiUrl: 'http://api.test/api/v1', supabaseUrl: 'http://auth.test', supabaseKey: 'public-key' },
}))

import { App } from './App'
import { AuthProvider } from './auth/AuthProvider'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status })
}

function okFetch() {
  return vi.fn<typeof fetch>(async (input) => {
    const path = new URL(String(input)).pathname
    if (path.endsWith('/transactions')) return json({ items: [], next_cursor: null })
    if (path.endsWith('/summary') || path.endsWith('/wealth')) return json({}, 404)
    return json([])
  })
}

function renderApp() {
  return render(
    <AuthProvider>
      <App />
    </AuthProvider>,
  )
}

beforeEach(() => {
  auth.getSession.mockResolvedValue({ data: { session } })
  auth.signOut.mockResolvedValue({ error: null })
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  auth.getSession.mockReset()
  auth.signOut.mockReset()
})

describe('session handling', () => {
  it('sends the access token with API calls', async () => {
    const fetchMock = okFetch()
    vi.stubGlobal('fetch', fetchMock)
    renderApp()
    await screen.findByRole('heading', { name: 'Inicio' })
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    // The first call is the health check that wakes the server, before any data; it needs no token.
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('http://api.test/api/v1/health')
    const call = fetchMock.mock.calls.find(([url]) => !String(url).endsWith('/health'))
    expect((call?.[1]?.headers as Record<string, string>).Authorization).toBe('Bearer token-abc')
  })

  it('signs out and shows the expired notice when the API answers 401', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json({ error: { code: 'invalid_token', message: 'Token inválido.', details: {} } }, 401)),
    )
    renderApp()
    expect(await screen.findByText('Tu sesión expiró. Inicia sesión de nuevo.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Iniciar sesión' })).toBeInTheDocument()
    expect(auth.signOut).toHaveBeenCalled()
  })

  it('clears the query cache when the session ends', async () => {
    vi.stubGlobal('fetch', okFetch())
    const clear = vi.spyOn(QueryClient.prototype, 'clear')
    renderApp()
    await screen.findByRole('heading', { name: 'Inicio' })
    expect(clear).not.toHaveBeenCalled()

    act(() => {
      ;(auth.listener as AuthListener)('SIGNED_OUT', null)
    })
    expect(await screen.findByRole('button', { name: 'Iniciar sesión' })).toBeInTheDocument()
    expect(clear).toHaveBeenCalled()
  })

  it('signs out from the menu', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', okFetch())
    renderApp()
    await screen.findByRole('heading', { name: 'Inicio' })
    await user.click(screen.getByRole('link', { name: /Más/ }))
    await user.click(await screen.findByRole('button', { name: 'Cerrar sesión' }))
    expect(await screen.findByRole('button', { name: 'Iniciar sesión' })).toBeInTheDocument()
    expect(auth.signOut).toHaveBeenCalled()
  })

  it('shows the login screen without a session', async () => {
    auth.getSession.mockResolvedValue({ data: { session: null } })
    vi.stubGlobal('fetch', okFetch())
    renderApp()
    expect(await screen.findByRole('button', { name: 'Iniciar sesión' })).toBeInTheDocument()
  })
})
