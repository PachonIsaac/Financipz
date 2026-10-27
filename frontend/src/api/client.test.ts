import { describe, expect, it, vi } from 'vitest'
import { ApiError, createApiClient, errorMessage } from './client'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function setup(response: Response | Error, token: string | null = 'token-123') {
  const fetchImpl = vi.fn<typeof fetch>(async () => {
    if (response instanceof Error) throw response
    return response
  })
  const onUnauthorized = vi.fn()
  const client = createApiClient({
    baseUrl: 'http://api.test/api/v1/',
    getToken: async () => token,
    onUnauthorized,
    fetchImpl,
  })
  return { client, fetchImpl, onUnauthorized }
}

describe('api client', () => {
  it('sends the bearer token and builds the query string', async () => {
    const { client, fetchImpl } = setup(jsonResponse(200, [{ id: 'a' }]))
    const result = await client.request('/accounts', { query: { archived: false, q: undefined, cursor: '' } })
    expect(result).toEqual([{ id: 'a' }])
    const [url, init] = fetchImpl.mock.calls[0]!
    expect(url).toBe('http://api.test/api/v1/accounts?archived=false')
    expect((init?.headers as Record<string, string>).Authorization).toBe('Bearer token-123')
  })

  it('omits the header without a token and sends JSON bodies', async () => {
    const { client, fetchImpl } = setup(jsonResponse(201, { id: 'x' }), null)
    await client.request('/accounts', { method: 'POST', body: { name: 'Caja' } })
    const [, init] = fetchImpl.mock.calls[0]!
    const headers = init?.headers as Record<string, string>
    expect(headers.Authorization).toBeUndefined()
    expect(headers['Content-Type']).toBe('application/json')
    expect(init?.body).toBe('{"name":"Caja"}')
    expect(init?.method).toBe('POST')
  })

  it('maps API errors to ApiError', async () => {
    const { client } = setup(
      jsonResponse(409, { error: { code: 'conflict', message: 'La cuenta ya existe.', details: {} } }),
    )
    await expect(client.request('/accounts')).rejects.toMatchObject({
      status: 409,
      code: 'conflict',
      message: 'La cuenta ya existe.',
    })
  })

  it('exposes field problems of validation errors', async () => {
    const { client } = setup(
      jsonResponse(422, {
        error: {
          code: 'validation_error',
          message: 'Revisa los datos enviados.',
          details: { fields: [{ field: 'amount', problem: 'Input should be greater than 0' }] },
        },
      }),
    )
    const error = await client.request('/transactions').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).fieldProblems).toEqual([{ field: 'amount', problem: 'Input should be greater than 0' }])
    expect(errorMessage(error)).toBe('Revisa los datos enviados. Monto debe ser mayor que cero.')
  })

  it('signs out on 401', async () => {
    const { client, onUnauthorized } = setup(
      jsonResponse(401, { error: { code: 'invalid_token', message: 'Token inválido.', details: {} } }),
    )
    await expect(client.request('/me')).rejects.toMatchObject({ status: 401, code: 'invalid_token' })
    expect(onUnauthorized).toHaveBeenCalledOnce()
  })

  it('does not sign out on other errors', async () => {
    const { client, onUnauthorized } = setup(jsonResponse(403, { error: { code: 'forbidden', message: 'No.', details: {} } }))
    await expect(client.request('/me')).rejects.toMatchObject({ status: 403 })
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it('returns undefined on 204', async () => {
    const { client } = setup(new Response(null, { status: 204 }))
    await expect(client.request('/categories/1', { method: 'DELETE' })).resolves.toBeUndefined()
  })

  it('reports network failures', async () => {
    const { client } = setup(new TypeError('failed'))
    await expect(client.request('/me')).rejects.toMatchObject({ status: 0, code: 'network_error' })
  })

  it('falls back to a generic error for non-JSON failures', async () => {
    const { client } = setup(new Response('boom', { status: 500 }))
    await expect(client.request('/me')).rejects.toMatchObject({ status: 500, code: 'http_error' })
  })

  it('gives up with a timeout error when the server takes too long', async () => {
    vi.useFakeTimers()
    const fetchImpl = vi.fn<typeof fetch>(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
        }),
    )
    const client = createApiClient({ baseUrl: 'http://api.test/api/v1', getToken: async () => null, onUnauthorized: vi.fn(), fetchImpl })

    const result = expect(client.request('/me', { timeoutMs: 5_000 })).rejects.toMatchObject({ status: 0, code: 'timeout' })
    await vi.advanceTimersByTimeAsync(5_000)

    await result
    vi.useRealTimers()
  })
})
