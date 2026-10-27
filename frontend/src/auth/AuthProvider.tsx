import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { SupabaseClient } from '@supabase/supabase-js'
import { config } from '../lib/config'

export type AuthStatus = 'loading' | 'signedIn' | 'signedOut'

export interface AuthValue {
  status: AuthStatus
  email: string | null
  /** True when the last sign out was forced by an expired or rejected token. */
  expired: boolean
  /** False when the auth settings are missing from the environment. */
  configured: boolean
  signIn(email: string, password: string): Promise<string | null>
  signOut(): Promise<void>
  /** Called by the API client on a 401. */
  handleUnauthorized(): void
  getToken(): Promise<string | null>
}

export const AuthContext = createContext<AuthValue | null>(null)

let cached: Promise<SupabaseClient | null> | undefined

const isConfigured = () => Boolean(config.supabaseUrl && config.supabaseKey)

/** The auth client is loaded on demand so it stays out of the initial bundle. */
function loadSupabase(): Promise<SupabaseClient | null> {
  if (cached === undefined) {
    cached = isConfigured()
      ? import('@supabase/supabase-js').then(({ createClient }) =>
          createClient(config.supabaseUrl, config.supabaseKey, {
            auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: false },
          }),
        )
      : Promise.resolve(null)
  }
  return cached
}

function signInMessage(raw: string): string {
  const text = raw.toLowerCase()
  if (text.includes('invalid login') || text.includes('invalid credentials')) {
    return 'Correo o contraseña incorrectos.'
  }
  if (text.includes('fetch') || text.includes('network')) {
    return 'No hay conexión. Revisa tu internet e intenta de nuevo.'
  }
  return 'No se pudo iniciar sesión. Intenta de nuevo.'
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const configured = isConfigured()
  const [status, setStatus] = useState<AuthStatus>(configured ? 'loading' : 'signedOut')
  const [email, setEmail] = useState<string | null>(null)
  const [expired, setExpired] = useState(false)
  const signingOut = useRef(false)

  useEffect(() => {
    let unsubscribe: (() => void) | undefined
    let cancelled = false
    void loadSupabase().then(async (supabase) => {
      if (!supabase || cancelled) return
      const { data } = await supabase.auth.getSession()
      if (cancelled) return
      setEmail(data.session?.user.email ?? null)
      setStatus(data.session ? 'signedIn' : 'signedOut')
      const listener = supabase.auth.onAuthStateChange((_event, session) => {
        setEmail(session?.user.email ?? null)
        setStatus(session ? 'signedIn' : 'signedOut')
      })
      unsubscribe = () => listener.data.subscription.unsubscribe()
    })
    return () => {
      cancelled = true
      unsubscribe?.()
    }
  }, [])

  const signIn = useCallback(async (emailValue: string, password: string): Promise<string | null> => {
    const supabase = await loadSupabase()
    if (!supabase) return 'Falta configurar el inicio de sesión de la aplicación.'
    try {
      const { error } = await supabase.auth.signInWithPassword({ email: emailValue, password })
      if (error) return signInMessage(error.message)
      setExpired(false)
      return null
    } catch (error) {
      return signInMessage(error instanceof Error ? error.message : '')
    }
  }, [])

  const signOut = useCallback(async () => {
    setExpired(false)
    const supabase = await loadSupabase()
    if (supabase) await supabase.auth.signOut()
    setStatus('signedOut')
  }, [])

  const handleUnauthorized = useCallback(() => {
    if (signingOut.current) return
    signingOut.current = true
    setExpired(true)
    setStatus('signedOut')
    void loadSupabase()
      .then((supabase) => supabase?.auth.signOut())
      .finally(() => {
        signingOut.current = false
      })
  }, [])

  const getToken = useCallback(async () => {
    const supabase = await loadSupabase()
    if (!supabase) return null
    const { data } = await supabase.auth.getSession()
    return data.session?.access_token ?? null
  }, [])

  const value = useMemo<AuthValue>(
    () => ({
      status,
      email,
      expired,
      configured,
      signIn,
      signOut,
      handleUnauthorized,
      getToken,
    }),
    [status, email, expired, configured, signIn, signOut, handleUnauthorized, getToken],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
