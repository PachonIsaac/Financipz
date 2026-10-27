import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

interface ToastValue {
  show(message: string): void
}

const ToastContext = createContext<ToastValue>({ show: () => undefined })

export function ToastProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    if (!message) return
    const timer = window.setTimeout(() => setMessage(null), 2500)
    return () => window.clearTimeout(timer)
  }, [message])

  const show = useCallback((text: string) => setMessage(text), [])
  const value = useMemo(() => ({ show }), [show])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-24 z-50 flex justify-center px-4"
      >
        {message ? (
          <p className="rounded-full bg-slate-900 px-4 py-2 text-sm text-white shadow-lg dark:bg-slate-100 dark:text-slate-900">
            {message}
          </p>
        ) : null}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastValue {
  return useContext(ToastContext)
}
