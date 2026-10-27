import { Suspense, lazy, useEffect, useMemo, useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { ApiProvider } from './api/ApiProvider'
import { ApiError, createApiClient } from './api/client'
import { createEndpoints } from './api/endpoints'
import { useAuth } from './auth/AuthProvider'
import { RouteErrorBoundary } from './components/ErrorBoundary'
import { AppLayout } from './components/Layout'
import { ToastProvider } from './components/Toast'
import { config } from './lib/config'

const AccountsScreen = lazy(() => import('./screens/Accounts').then((m) => ({ default: m.AccountsScreen })))
const CategoriesScreen = lazy(() => import('./screens/Categories').then((m) => ({ default: m.CategoriesScreen })))
const HomeScreen = lazy(() => import('./screens/Home').then((m) => ({ default: m.HomeScreen })))
const LoginScreen = lazy(() => import('./screens/Login').then((m) => ({ default: m.LoginScreen })))
const MoreScreen = lazy(() => import('./screens/More').then((m) => ({ default: m.MoreScreen })))
const MovementDetailScreen = lazy(() => import('./screens/MovementDetail').then((m) => ({ default: m.MovementDetailScreen })))
const MovementsScreen = lazy(() => import('./screens/Movements').then((m) => ({ default: m.MovementsScreen })))
const NewTransactionScreen = lazy(() => import('./screens/NewTransaction').then((m) => ({ default: m.NewTransactionScreen })))
const ReviewScreen = lazy(() => import('./screens/Review').then((m) => ({ default: m.ReviewScreen })))

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
    <RouteErrorBoundary>
    <Suspense fallback={<div role="status" aria-label="Cargando" className="min-h-dvh" />}>
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
    </Suspense>
    </RouteErrorBoundary>
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
    return (
      <Suspense fallback={null}>
        <LoginScreen />
      </Suspense>
    )
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
