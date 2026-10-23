import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api, ApiError, setRefreshHandler, setToken } from '../lib/api'
import { getInitData } from '../lib/telegram'
import type { Session, User, Wallet } from '../lib/types'

type AuthState =
  | { status: 'loading' }
  | { status: 'ready'; user: User; wallet: Wallet }
  | { status: 'error'; reason: 'not_in_telegram' | 'login_failed'; message: string }

interface AuthContextValue {
  state: AuthState
  /** Re-read the wallet after something changed it (a prediction, for example). */
  setWallet: (wallet: Wallet) => void
  retry: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

const DEV_ID = Number(import.meta.env.VITE_DEV_TELEGRAM_ID || 0)

async function login(): Promise<Session> {
  const initData = getInitData()
  if (initData) {
    return api<Session>('/auth/telegram', { method: 'POST', body: { init_data: initData }, retryOn401: false })
  }
  if (import.meta.env.DEV && DEV_ID > 0) {
    return api<Session>('/auth/dev', {
      method: 'POST',
      body: { telegram_id: DEV_ID, display_name: 'Dev User' },
      retryOn401: false,
    })
  }
  throw new ApiError(0, 'not_in_telegram', 'Open this app from Telegram.')
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading' })
  const inFlight = useRef<Promise<boolean> | null>(null)

  const start = useCallback(async (): Promise<boolean> => {
    try {
      const session = await login()
      setToken(session.access_token)
      setState({ status: 'ready', user: session.user, wallet: session.wallet })
      return true
    } catch (error) {
      setToken(null)
      const notInTelegram = error instanceof ApiError && error.code === 'not_in_telegram'
      setState({
        status: 'error',
        reason: notInTelegram ? 'not_in_telegram' : 'login_failed',
        message: error instanceof ApiError ? error.message : 'Login failed. Please try again.',
      })
      return false
    }
  }, [])

  // One shared re-login, even if several requests hit an expired token at the same moment.
  const refresh = useCallback((): Promise<boolean> => {
    if (!inFlight.current) {
      inFlight.current = start().finally(() => {
        inFlight.current = null
      })
    }
    return inFlight.current
  }, [start])

  useEffect(() => {
    setRefreshHandler(refresh)
    void refresh()
    return () => setRefreshHandler(null)
  }, [refresh])

  const value = useMemo<AuthContextValue>(
    () => ({
      state,
      setWallet: (wallet) => setState((current) => (current.status === 'ready' ? { ...current, wallet } : current)),
      retry: () => {
        setState({ status: 'loading' })
        void refresh()
      },
    }),
    [state, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside <AuthProvider>')
  return value
}

/** For screens that only render when logged in. */
export function useSession(): { user: User; wallet: Wallet; setWallet: (wallet: Wallet) => void } {
  const { state, setWallet } = useAuth()
  if (state.status !== 'ready') throw new Error('useSession used before login finished')
  return { user: state.user, wallet: state.wallet, setWallet }
}
