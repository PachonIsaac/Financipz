import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthValue } from '../auth/AuthProvider'
import { LoginScreen } from './Login'

function renderLogin(overrides: Partial<AuthValue> = {}) {
  const value: AuthValue = {
    status: 'signedOut',
    email: null,
    expired: false,
    configured: true,
    signIn: vi.fn(async () => null),
    signOut: vi.fn(async () => undefined),
    handleUnauthorized: vi.fn(),
    getToken: vi.fn(async () => null),
    ...overrides,
  }
  render(
    <AuthContext.Provider value={value}>
      <LoginScreen />
    </AuthContext.Provider>,
  )
  return value
}

describe('login screen', () => {
  it('has no sign-up option', () => {
    renderLogin()
    expect(screen.queryByText(/registr|crear cuenta/i)).not.toBeInTheDocument()
  })

  it('submits the credentials', async () => {
    const user = userEvent.setup()
    const auth = renderLogin()
    await user.type(screen.getByLabelText('Correo electrónico'), 'persona@example.com')
    await user.type(screen.getByLabelText('Contraseña'), 'secreto')
    await user.click(screen.getByRole('button', { name: 'Iniciar sesión' }))
    expect(auth.signIn).toHaveBeenCalledWith('persona@example.com', 'secreto')
  })

  it('shows the error returned by sign in', async () => {
    const user = userEvent.setup()
    renderLogin({ signIn: vi.fn(async () => 'Correo o contraseña incorrectos.') })
    await user.type(screen.getByLabelText('Correo electrónico'), 'persona@example.com')
    await user.type(screen.getByLabelText('Contraseña'), 'mala')
    await user.click(screen.getByRole('button', { name: 'Iniciar sesión' }))
    expect(await screen.findByText('Correo o contraseña incorrectos.')).toBeInTheDocument()
  })

  it('validates empty fields without calling sign in', async () => {
    const user = userEvent.setup()
    const auth = renderLogin()
    await user.click(screen.getByRole('button', { name: 'Iniciar sesión' }))
    expect(screen.getByText('Escribe tu correo y tu contraseña.')).toBeInTheDocument()
    expect(auth.signIn).not.toHaveBeenCalled()
  })

  it('tells the user when the session expired', () => {
    renderLogin({ expired: true })
    expect(screen.getByText('Tu sesión expiró. Inicia sesión de nuevo.')).toBeInTheDocument()
  })
})
