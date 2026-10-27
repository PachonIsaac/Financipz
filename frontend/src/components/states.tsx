import { useEffect, useState, type ReactNode } from 'react'
import { ApiError, errorMessage } from '../api/client'
import type { WarmupState } from '../api/useWarmup'
import { Button } from './ui'

/** Placeholder rows while data loads. After 3 seconds it says the server is waking up. */
export function ListSkeleton({ rows = 4, label = 'Cargando' }: { rows?: number; label?: string }) {
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    const timer = window.setTimeout(() => setSlow(true), 3000)
    return () => window.clearTimeout(timer)
  }, [])
  return (
    <div role="status" aria-live="polite" aria-label={label} className="flex flex-col gap-2">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="h-14 animate-pulse rounded-xl bg-slate-200 dark:bg-slate-800" />
      ))}
      {slow ? <p className="text-center text-sm text-slate-500 dark:text-slate-400">Conectando…</p> : null}
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const offline = error instanceof ApiError && error.code === 'network_error'
  return (
    <div role="alert" className="flex flex-col items-center gap-3 rounded-2xl p-6 text-center">
      <p className="text-base font-medium">{offline ? 'Sin conexión' : 'Algo salió mal'}</p>
      <p className="text-sm text-slate-600 dark:text-slate-400">{errorMessage(error)}</p>
      {onRetry ? (
        <Button variant="secondary" onClick={onRetry}>
          Reintentar
        </Button>
      ) : null}
    </div>
  )
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center gap-2 p-8 text-center">
      <p className="text-base font-medium">{title}</p>
      {description ? <p className="text-sm text-slate-600 dark:text-slate-400">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  )
}

export function FormError({ error }: { error: unknown }) {
  if (!error) return null
  return (
    <p role="alert" className="rounded-xl bg-red-100 p-3 text-sm text-red-800 dark:bg-red-950 dark:text-red-200">
      {errorMessage(error)}
    </p>
  )
}

/** Banner shown while the device reports no connection. */
export function OfflineBanner() {
  const [online, setOnline] = useState(() => navigator.onLine)
  useEffect(() => {
    const on = () => setOnline(true)
    const off = () => setOnline(false)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => {
      window.removeEventListener('online', on)
      window.removeEventListener('offline', off)
    }
  }, [])
  if (online) return null
  return (
    <p role="status" className="bg-amber-200 px-4 pb-2 pt-[max(0.5rem,env(safe-area-inset-top))] text-center text-sm text-amber-900">
      Sin conexión. Mostrando los últimos datos cargados.
    </p>
  )
}

/** Says the server is waking up, once it has taken a couple of seconds. It never blocks signing in. */
export function WarmupBanner({ state, onRetry }: { state: WarmupState; onRetry: () => void }) {
  if (state.status === 'ready') return null
  if (state.status === 'checking') {
    if (state.seconds < 2) return null
    return (
      <p role="status" className="bg-slate-200 px-4 py-2 text-center text-sm text-slate-700 dark:bg-slate-800 dark:text-slate-200">
        Despertando el servidor… {state.seconds} s
      </p>
    )
  }
  return (
    <div role="alert" className="flex items-center justify-center gap-3 bg-amber-200 px-4 py-2 text-sm text-amber-900">
      <span>No se pudo despertar el servidor.</span>
      <button type="button" onClick={onRetry} className="min-h-11 font-semibold underline">
        Reintentar
      </button>
    </div>
  )
}
