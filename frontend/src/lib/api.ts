// Small fetch wrapper for the WienerDoge API.
// - Sends the session token as a Bearer header (token lives in memory only, never in storage).
// - Turns the API's {"error": {"code", "message"}} replies into ApiError.
// - On a 401 it asks the auth layer to log in again once, then retries the request.

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details?: unknown

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

const BASE = ((import.meta.env.VITE_API_URL as string | undefined) || '/api/v1').replace(/\/+$/, '')

let token: string | null = null
let refreshHandler: (() => Promise<boolean>) | null = null

export function setToken(value: string | null): void {
  token = value
}

export function getToken(): string | null {
  return token
}

/** The auth layer registers how to get a fresh session when the token has expired. */
export function setRefreshHandler(handler: (() => Promise<boolean>) | null): void {
  refreshHandler = handler
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH'
  body?: unknown
  headers?: Record<string, string>
  signal?: AbortSignal
  /** Set false for calls that must not trigger a re-login (the login calls themselves). */
  retryOn401?: boolean
}

function newRequestError(response: Response, payload: unknown): ApiError {
  const error = (payload as { error?: { code?: string; message?: string; details?: unknown } } | null)?.error
  return new ApiError(
    response.status,
    error?.code ?? `http_${response.status}`,
    error?.message ?? 'Something went wrong. Please try again.',
    error?.details,
  )
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, headers = {}, signal, retryOn401 = true } = options

  const send = async (): Promise<Response> => {
    const finalHeaders: Record<string, string> = { Accept: 'application/json', ...headers }
    if (body !== undefined) finalHeaders['Content-Type'] = 'application/json'
    if (token) finalHeaders.Authorization = `Bearer ${token}`
    try {
      return await fetch(`${BASE}${path}`, {
        method,
        headers: finalHeaders,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal,
      })
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
      throw new ApiError(0, 'network_error', 'Cannot reach the server. Check your connection and try again.')
    }
  }

  let response = await send()
  if (response.status === 401 && retryOn401 && refreshHandler && token) {
    if (await refreshHandler()) response = await send()
  }

  let payload: unknown = null
  try {
    payload = await response.json()
  } catch {
    /* empty or non-JSON body */
  }
  if (!response.ok) throw newRequestError(response, payload)
  return payload as T
}

/** A fresh random key for one user action (one tap on "Place prediction"). Reuse it only to retry that same action. */
export function newIdempotencyKey(): string {
  return crypto.randomUUID()
}
