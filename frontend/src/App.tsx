import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Route, Routes, BrowserRouter } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { Layout } from './components/Layout'
import { ErrorState, Spinner } from './components/ui'
import AdminPage from './pages/Admin'
import ComingSoon from './pages/ComingSoon'
import HistoryPage from './pages/History'
import LeaderboardPage from './pages/Leaderboard'
import MarketsPage from './pages/Markets'
import ProfilePage from './pages/Profile'
import VipPage from './pages/Vip'
import WalletPage from './pages/Wallet'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 15_000 } },
})

function Gate() {
  const { state, retry } = useAuth()

  if (state.status === 'loading') return <Spinner label="Signing in" />

  if (state.status === 'error') {
    return (
      <div className="mx-auto mt-24 max-w-sm px-4">
        <ErrorState
          message={
            state.reason === 'not_in_telegram'
              ? 'Please open WienerDoge from Telegram (send /start to the bot and tap Open WienerDoge).'
              : state.message
          }
          onRetry={state.reason === 'login_failed' ? retry : undefined}
        />
      </div>
    )
  }

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<MarketsPage />} />
        <Route path="wallet" element={<WalletPage />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="vip" element={<VipPage />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="admin" element={<AdminPage />} />
        <Route path="leaderboard" element={<LeaderboardPage />} />
        <Route path="*" element={<ComingSoon title="Not found" />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Gate />
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}
