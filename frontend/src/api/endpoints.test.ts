import { describe, expect, it, vi } from 'vitest'
import { createApiClient } from './client'
import { createEndpoints } from './endpoints'

function setup(status = 200, body: unknown = {}) {
  const fetchImpl = vi.fn<typeof fetch>(async () =>
    status === 204 ? new Response(null, { status }) : new Response(JSON.stringify(body), { status }),
  )
  const api = createEndpoints(
    createApiClient({
      baseUrl: 'http://api.test/api/v1',
      getToken: async () => 't',
      onUnauthorized: () => undefined,
      fetchImpl,
    }),
  )
  const last = () => {
    const [url, init] = fetchImpl.mock.calls.at(-1)!
    const parsed = new URL(String(url))
    return {
      method: init?.method,
      path: parsed.pathname,
      query: Object.fromEntries(parsed.searchParams),
      body: init?.body ? (JSON.parse(String(init.body)) as unknown) : undefined,
    }
  }
  return { api, last }
}

describe('endpoint contracts', () => {
  it('lists transactions with the backend filter names', async () => {
    const { api, last } = setup(200, { items: [], next_cursor: null })
    await api.listTransactions(
      {
        from: '2026-10-01',
        to: '2026-10-31',
        account_id: 'a',
        category_id: 'c',
        type: 'expense',
        status: 'pending_review',
        q: 'cafe',
      },
      'cur',
      10,
    )
    expect(last()).toMatchObject({
      method: 'GET',
      path: '/api/v1/transactions',
      query: {
        from: '2026-10-01',
        to: '2026-10-31',
        account_id: 'a',
        category_id: 'c',
        type: 'expense',
        status: 'pending_review',
        q: 'cafe',
        cursor: 'cur',
        limit: '10',
      },
    })
  })

  it('creates a transaction with a JSON body', async () => {
    const { api, last } = setup(201, {})
    await api.createTransaction({ account_id: 'a', type: 'expense', amount: '10.00' })
    expect(last()).toMatchObject({
      method: 'POST',
      path: '/api/v1/transactions',
      body: { account_id: 'a', type: 'expense', amount: '10.00' },
    })
  })

  it('patches accounts and posts adjustments', async () => {
    const { api, last } = setup()
    await api.updateAccount('x', { archived: true })
    expect(last()).toMatchObject({ method: 'PATCH', path: '/api/v1/accounts/x', body: { archived: true } })
    await api.adjustAccount('x', { observed_balance: '5.00', note: 'conteo' })
    expect(last()).toMatchObject({
      method: 'POST',
      path: '/api/v1/accounts/x/adjustments',
      body: { observed_balance: '5.00', note: 'conteo' },
    })
  })

  it('replaces identifiers wrapped in an object', async () => {
    const { api, last } = setup(200, [])
    await api.replaceIdentifiers('x', [{ digits: '1234', type: 'debit' }])
    expect(last()).toMatchObject({
      method: 'PUT',
      path: '/api/v1/accounts/x/identifiers',
      body: { identifiers: [{ digits: '1234', type: 'debit' }] },
    })
  })

  it('deletes a category with reassign_to and no body', async () => {
    const { api, last } = setup(204)
    await api.deleteCategory('c1', 'c2')
    expect(last()).toMatchObject({ method: 'DELETE', path: '/api/v1/categories/c1', query: { reassign_to: 'c2' } })
    expect(last().body).toBeUndefined()
  })

  it('confirms, discards and reads reports', async () => {
    const { api, last } = setup()
    await api.confirmTransaction('t')
    expect(last()).toMatchObject({ method: 'POST', path: '/api/v1/transactions/t/confirm' })
    await api.discardTransaction('t')
    expect(last()).toMatchObject({ method: 'POST', path: '/api/v1/transactions/t/discard' })
    await api.getSummary('2026-10')
    expect(last()).toMatchObject({ path: '/api/v1/summary', query: { month: '2026-10' } })
    await api.getWealth()
    expect(last()).toMatchObject({ path: '/api/v1/wealth' })
  })
})
