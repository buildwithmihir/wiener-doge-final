import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, setRefreshHandler, setToken } from './api'

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

describe('api client', () => {
  beforeEach(() => {
    setToken(null)
    setRefreshHandler(null)
  })
  afterEach(() => vi.restoreAllMocks())

  it('returns parsed JSON and sends the bearer token', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(200, { ok: true }))
    setToken('abc')
    expect(await api<{ ok: boolean }>('/wallet')).toEqual({ ok: true })
    const [url, init] = spy.mock.calls[0]!
    expect(String(url)).toBe('/api/v1/wallet')
    expect((init!.headers as Record<string, string>).Authorization).toBe('Bearer abc')
  })

  it('turns API errors into ApiError with the server code', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json(400, { error: { code: 'insufficient_balance', message: 'Not enough demo credits.' } }),
    )
    await expect(api('/predictions', { method: 'POST', body: {} })).rejects.toMatchObject({
      name: 'ApiError',
      status: 400,
      code: 'insufficient_balance',
      message: 'Not enough demo credits.',
    })
  })

  it('reports a network failure with a friendly message', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    const error = await api('/wallet').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('network_error')
  })

  it('re-logs in once on 401 and retries with the new token', async () => {
    const spy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json(401, { error: { code: 'token_expired', message: 'Session expired.' } }))
      .mockResolvedValueOnce(json(200, { ok: 1 }))
    setToken('old')
    setRefreshHandler(async () => {
      setToken('new')
      return true
    })
    expect(await api('/wallet')).toEqual({ ok: 1 })
    expect(spy).toHaveBeenCalledTimes(2)
    expect(((spy.mock.calls[1]![1]!.headers) as Record<string, string>).Authorization).toBe('Bearer new')
  })

  it('does not loop when the retry is still unauthorized', async () => {
    const spy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(json(401, { error: { code: 'invalid_token', message: 'Invalid session.' } }))
    setToken('old')
    setRefreshHandler(async () => true)
    await expect(api('/wallet')).rejects.toMatchObject({ status: 401, code: 'invalid_token' })
    expect(spy).toHaveBeenCalledTimes(2)
  })

  it('never retries the login calls themselves', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(401, { error: { code: 'initdata_invalid', message: 'x' } }))
    setToken('t')
    setRefreshHandler(async () => true)
    await expect(api('/auth/telegram', { method: 'POST', body: {}, retryOn401: false })).rejects.toBeInstanceOf(ApiError)
    expect(spy).toHaveBeenCalledTimes(1)
  })

  it('handles non-JSON error bodies', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('Bad gateway', { status: 502 }))
    await expect(api('/markets')).rejects.toMatchObject({ status: 502, code: 'http_502' })
  })
})
