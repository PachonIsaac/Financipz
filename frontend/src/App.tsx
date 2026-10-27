import { useEffect, useMemo, useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { ApiProvider } from './api/ApiProvider'
import { ApiError, createApiClient } from './api/client'
import { createEndpoints } from './api/endpoints'
import { useAuth } from './auth/AuthProvider'
import { AppLayout } from './components/Layout'
import { ToastProvider } from './components/Toast'
import { config } from './lib/config'
import { AccountsScreen } from './screens/Accounts'
import { CategoriesScreen } from './screens/Categories'
import { HomeScreen } from './screens/Home'
import { LoginScreen } from './screens/Login'
import { MoreScreen } from './screens/More'
import { MovementDetailScreen } from './screens/MovementDetail'
import { MovementsScreen } from './screens/Movements'
import { NewTransactionScreen } from './screens/NewTransaction'
import { ReviewScreen } from './screens/Review'

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: (count, error) => !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 2,
      },
    },
  })
}

/** Routes for a signed-in user. */
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/new" element={<NewTransactionScreen />} />
      <Route element={<AppLayout />}>
        <Route index element={<HomeScreen />} />
        <Route path="movements" element={<MovementsScreen />} />
        <Route path="movements/:id" element={<MovementDetailScreen />} />
        <Route path="review" element={<ReviewScreen />} />
        <Route path="more" element={<MoreScreen />} />
        <Route path="more/accounts" element={<AccountsScreen />} />
        <Route path="more/categories" element={<CategoriesScreen />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export function App() {
  const auth = useAuth()
  const [queryClient] = useState(() => createQueryClient())
  const { getToken, handleUnauthorized } = auth
  const api = useMemo(
    () =>
      createEndpoints(
        createApiClient({ baseUrl: config.apiUrl, getToken, onUnauthorized: handleUnauthorized }),
      ),
    [getToken, handleUnauthorized],
  )

  useEffect(() => {
    if (auth.status === 'signedOut') queryClient.clear()
  }, [auth.status, queryClient])

  if (auth.status === 'loading') {
    return <div role="status" aria-label="Cargando" className="min-h-dvh" />
  }
  if (auth.status === 'signedOut') {
    return <LoginScreen />
  }

  return (
    <QueryClientProvider client={queryClient}>
      <ApiProvider api={api}>
        <ToastProvider>
          <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, '')}>
            <AppRoutes />
          </BrowserRouter>
        </ToastProvider>
      </ApiProvider>
    </QueryClientProvider>
  )
}
