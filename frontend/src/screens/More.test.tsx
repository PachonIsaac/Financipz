import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { writeStored } from '../lib/storage'
import { fakeApi, renderWithApp, stubLocalStorage } from '../test/utils'
import { MoreScreen } from './More'

vi.mock('../auth/AuthProvider', () => ({ useAuth: () => ({ email: 'persona@example.com', signOut: vi.fn() }) }))

beforeEach(stubLocalStorage)

describe('wake-up diagnostics', () => {
  it('says there is nothing recorded yet', () => {
    renderWithApp(<MoreScreen />, { api: fakeApi() })

    expect(screen.getByText('Aún no hay despertares del servidor registrados.')).toBeInTheDocument()
  })

  it('shows the last wake-up and the average of the latest ones', () => {
    writeStored(
      'financipz.wakeups',
      JSON.stringify([
        { at: '2026-10-25T15:00:00Z', seconds: 60 },
        { at: '2026-10-26T15:00:00Z', seconds: 40 },
      ]),
    )

    renderWithApp(<MoreScreen />, { api: fakeApi() })

    expect(screen.getByText(/Último despertar del servidor: 40 s/)).toBeInTheDocument()
    expect(screen.getByText(/Promedio de los últimos 2: 50 s/)).toBeInTheDocument()
  })
})
