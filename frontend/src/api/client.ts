// Thin fetch wrapper for the backend: bearer token, error mapping and 401 handling.

export interface FieldProblem {
  field: string
  problem: string
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }

  /** Per-field problems of a `validation_error`, empty for any other error. */
  get fieldProblems(): FieldProblem[] {
    const fields = this.details.fields
    if (this.code !== 'validation_error' || !Array.isArray(fields)) return []
    return fields.flatMap((item): FieldProblem[] => {
      if (item && typeof item === 'object' && 'field' in item && 'problem' in item) {
        const { field, problem } = item as { field: unknown; problem: unknown }
        return [{ field: String(field), problem: String(problem) }]
      }
      return []
    })
  }
}

/** Short Spanish text for a Pydantic problem message. */
export function translateProblem(problem: string): string {
  const text = problem.toLowerCase()
  if (text.includes('field required') || text.includes('cannot be null')) return 'es obligatorio'
  if (text.includes('greater than 0') || text.includes('greater than zero')) return 'debe ser mayor que cero'
  if (text.includes('greater than')) return 'es demasiado bajo'
  if (text.includes('less than')) return 'es demasiado alto'
  if (text.includes('at most') || text.includes('too long') || text.includes('decimal places')) {
    return text.includes('decimal') ? 'tiene demasiados decimales' : 'es demasiado largo'
  }
  if (text.includes('at least') || text.includes('too short')) return 'es demasiado corto'
  if (text.includes('digits')) return 'tiene demasiados dígitos'
  if (text.includes('pattern') || text.includes('valid') || text.includes('should match')) return 'no tiene un formato válido'
  return 'no es válido'
}

const FIELD_LABELS: Record<string, string> = {
  amount: 'Monto',
  target_amount: 'Monto recibido',
  account_id: 'Cuenta',
  target_account_id: 'Cuenta destino',
  category_id: 'Categoría',
  merchant: 'Comercio',
  note: 'Nota',
  date: 'Fecha',
  name: 'Nombre',
  key: 'Llave',
  counterparty: 'Persona',
  initial_balance: 'Saldo inicial',
  observed_balance: 'Saldo real',
  digits: 'Dígitos',
  parent_id: 'Categoría principal',
}

export function fieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? 'Dato'
}

/** Human-readable message for any thrown value. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const problems = error.fieldProblems
    if (problems.length > 0) {
      return `${error.message} ${problems.map((p) => `${fieldLabel(p.field)} ${translateProblem(p.problem)}.`).join(' ')}`
    }
    return error.message
  }
  return 'Ocurrió un error inesperado.'
}

export interface ApiClientOptions {
  baseUrl: string
  getToken: () => Promise<string | null>
  onUnauthorized: () => void
  fetchImpl?: typeof fetch
}

export type QueryParams = Record<string, string | number | boolean | undefined | null>

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  query?: QueryParams
}

export interface ApiClient {
  request<T>(path: string, options?: RequestOptions): Promise<T>
}

function buildUrl(baseUrl: string, path: string, query?: QueryParams): string {
  const url = `${baseUrl.replace(/\/+$/, '')}${path}`
  if (!query) return url
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') {
      search.set(key, String(value))
    }
  }
  const text = search.toString()
  return text ? `${url}?${text}` : url
}

async function readError(response: Response): Promise<ApiError> {
  try {
    const data: unknown = await response.json()
    if (data && typeof data === 'object' && 'error' in data) {
      const error = (data as { error: { code?: unknown; message?: unknown; details?: unknown } }).error
      return new ApiError(
        response.status,
        typeof error.code === 'string' ? error.code : 'http_error',
        typeof error.message === 'string' ? error.message : 'No se pudo completar la solicitud.',
        error.details && typeof error.details === 'object' ? (error.details as Record<string, unknown>) : {},
      )
    }
  } catch {
    // Body was not JSON; fall through to the generic error.
  }
  return new ApiError(response.status, 'http_error', 'No se pudo completar la solicitud.')
}

export function createApiClient(options: ApiClientOptions): ApiClient {
  const doFetch = options.fetchImpl ?? ((...args: Parameters<typeof fetch>) => fetch(...args))

  async function request<T>(path: string, req: RequestOptions = {}): Promise<T> {
    const headers: Record<string, string> = { Accept: 'application/json' }
    const token = await options.getToken()
    if (token) headers.Authorization = `Bearer ${token}`
    if (req.body !== undefined) headers['Content-Type'] = 'application/json'

    let response: Response
    try {
      response = await doFetch(buildUrl(options.baseUrl, path, req.query), {
        method: req.method ?? 'GET',
        headers,
        body: req.body !== undefined ? JSON.stringify(req.body) : undefined,
      })
    } catch {
      throw new ApiError(0, 'network_error', 'No hay conexión con el servidor. Revisa tu internet e intenta de nuevo.')
    }

    if (response.status === 401) {
      options.onUnauthorized()
      const error = await readError(response)
      throw new ApiError(401, error.code, 'Tu sesión expiró. Inicia sesión de nuevo.', error.details)
    }
    if (!response.ok) {
      throw await readError(response)
    }
    if (response.status === 204) {
      return undefined as T
    }
    return (await response.json()) as T
  }

  return { request }
}
