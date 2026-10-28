import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { fakeApi, renderWithApp } from '../test/utils'
import { ShortcutScreen } from './Shortcut'

vi.mock('../lib/config', () => ({ config: { apiUrl: 'https://api.test/api/v1', supabaseUrl: '', supabaseKey: '' } }))

describe('iOS shortcut token', () => {
  it('invites to create a token when there is none and shows it once after creating it', async () => {
    const rotateShortcutToken = vi.fn(async () => ({ token: 'fzi_secret-token-value', created_at: '2026-10-28T20:00:00Z' }))
    const getShortcutToken = vi
      .fn()
      .mockResolvedValueOnce({ configured: false, created_at: null, last_used_at: null })
      .mockResolvedValue({ configured: true, created_at: '2026-10-28T20:00:00Z', last_used_at: null })
    renderWithApp(<ShortcutScreen />, { api: fakeApi({ getShortcutToken, rotateShortcutToken }) })

    expect(await screen.findByText(/Todavía no hay token/)).toBeInTheDocument()
    expect(screen.getByText('https://api.test/api/v1/ingest/shortcut')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Generar token' }))

    expect(await screen.findByTestId('token')).toHaveTextContent('fzi_secret-token-value')
    expect(screen.getByText('Cópialo ahora: no se vuelve a mostrar.')).toBeInTheDocument()
  })

  it('asks before replacing an existing token and never shows the stored one', async () => {
    const rotateShortcutToken = vi.fn(async () => ({ token: 'fzi_new', created_at: '2026-10-28T21:00:00Z' }))
    const getShortcutToken = vi.fn(async () => ({ configured: true, created_at: '2026-10-28T20:00:00Z', last_used_at: '2026-10-28T20:30:00Z' }))
    renderWithApp(<ShortcutScreen />, { api: fakeApi({ getShortcutToken, rotateShortcutToken }) })

    await userEvent.click(await screen.findByRole('button', { name: 'Generar un token nuevo' }))
    expect(rotateShortcutToken).not.toHaveBeenCalled()
    expect(screen.queryByTestId('token')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Generar uno nuevo' }))

    expect(await screen.findByTestId('token')).toHaveTextContent('fzi_new')
  })
})
