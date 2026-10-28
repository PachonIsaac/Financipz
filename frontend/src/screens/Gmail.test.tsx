import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import type { Integration } from '../api/types'
import { fakeApi, renderWithApp } from '../test/utils'
import { GmailScreen } from './Gmail'

const connected: Integration = { provider: 'gmail', status: 'active', last_synced_at: '2026-10-28T20:00:00Z', warnings: [] }

function setup(integration: Integration | null, overrides = {}, route = '/') {
  const api = fakeApi({ listIntegrations: vi.fn(async () => (integration ? [integration] : [])), ...overrides })
  renderWithApp(<GmailScreen />, { api, route })
  return api
}

afterEach(() => vi.unstubAllGlobals())

describe('mail connection', () => {
  it('opens the consent page that the server asks for', async () => {
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, assign })
    setup(null, { connectGmail: vi.fn(async () => ({ authorization_url: 'https://accounts.example/consent?x=1' })) })

    await userEvent.click(await screen.findByRole('button', { name: 'Conectar Gmail' }))

    await waitFor(() => expect(assign).toHaveBeenCalledWith('https://accounts.example/consent?x=1'))
  })

  it('shows why connecting failed on the server', async () => {
    setup(null, { connectGmail: vi.fn(async () => { throw new ApiError(503, 'gmail_not_configured', 'La lectura del correo no está configurada en el servidor.') }) })

    await userEvent.click(await screen.findByRole('button', { name: 'Conectar Gmail' }))

    expect(await screen.findByText('La lectura del correo no está configurada en el servidor.')).toBeInTheDocument()
  })

  it('reads the mail and says what happened to the messages', async () => {
    const syncGmail = vi.fn(async () => ({ processed: 5, created: 2, duplicates: 0, ignored: 2, unrecognized: 1, last_synced_at: '2026-10-28T21:00:00Z' }))
    setup(connected, { syncGmail })

    await userEvent.click(await screen.findByRole('button', { name: 'Leer ahora' }))

    expect(await screen.findByText('Correos leídos: 5.')).toBeInTheDocument()
    expect(screen.getByText('Movimientos nuevos para revisar: 2.')).toBeInTheDocument()
    expect(screen.getByText('Avisos que no son movimientos: 2.')).toBeInTheDocument()
    expect(screen.getByText('Correos que no se reconocieron: 1.')).toBeInTheDocument()
  })

  it('says so when there is nothing new', async () => {
    setup(connected, { syncGmail: vi.fn(async () => ({ processed: 0, created: 0, duplicates: 0, ignored: 0, unrecognized: 0, last_synced_at: '2026-10-28T21:00:00Z' })) })

    await userEvent.click(await screen.findByRole('button', { name: 'Leer ahora' }))

    expect(await screen.findByText('No hay correos nuevos del banco.')).toBeInTheDocument()
  })

  it('asks before disconnecting', async () => {
    const disconnectGmail = vi.fn(async () => undefined)
    setup(connected, { disconnectGmail })

    await userEvent.click(await screen.findByRole('button', { name: 'Desconectar' }))
    expect(disconnectGmail).not.toHaveBeenCalled()
    const dialog = screen.getByRole('alertdialog')
    await userEvent.click([...dialog.querySelectorAll('button')].find((b) => b.textContent === 'Desconectar')!)

    await waitFor(() => expect(disconnectGmail).toHaveBeenCalled())
  })

  it('tells the person how coming back from the consent page went', async () => {
    setup(null, {}, '/?connected=1')
    expect(await screen.findByText(/Gmail quedó conectado/)).toBeInTheDocument()
  })

  it('explains a refused return and a withdrawn permission', async () => {
    setup({ ...connected, status: 'error', warnings: [{ code: 'access_revoked', message: 'Google retiró el permiso.' }] }, {}, '/?error=access_denied')

    expect(await screen.findByText(/No se concedió el permiso de lectura/)).toBeInTheDocument()
    expect(await screen.findByText('Google retiró el permiso.')).toBeInTheDocument()
  })
})
