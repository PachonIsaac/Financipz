import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createClient, type SupabaseClient } from '@supabase/supabase-js'
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

let cached: SupabaseClient | null | undefined

function getSupabase(): SupabaseClient | null {
  if (cached === undefined) {
    cached =
      config.supabaseUrl && config.supabaseKey
        ? createClient(config.supabaseUrl, config.supabaseKey, {
            auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: false },
          })
        : null
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
  const supabase = getSupabase()
  const [status, setStatus] = useState<AuthStatus>(supabase ? 'loading' : 'signedOut')
  const [email, setEmail] = useState<string | null>(null)
  const [expired, setExpired] = useState(false)
  const signingOut = useRef(false)

  useEffect(() => {
    if (!supabase) return
    void supabase.auth.getSession().then(({ data }) => {
      setEmail(data.session?.user.email ?? null)
      setStatus(data.session ? 'signedIn' : 'signedOut')
    })
    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      setEmail(session?.user.email ?? null)
      setStatus(session ? 'signedIn' : 'signedOut')
    })
    return () => data.subscription.unsubscribe()
  }, [supabase])

  const signIn = useCallback(
    async (emailValue: string, password: string): Promise<string | null> => {
      if (!supabase) return 'Falta configurar el inicio de sesión de la aplicación.'
      try {
        const { error } = await supabase.auth.signInWithPassword({ email: emailValue, password })
        if (error) return signInMessage(error.message)
        setExpired(false)
        return null
      } catch (error) {
        return signInMessage(error instanceof Error ? error.message : '')
      }
    },
    [supabase],
  )

  const signOut = useCallback(async () => {
    setExpired(false)
    if (supabase) await supabase.auth.signOut()
    setStatus('signedOut')
  }, [supabase])

  const handleUnauthorized = useCallback(() => {
    if (signingOut.current) return
    signingOut.current = true
    setExpired(true)
    setStatus('signedOut')
    void (supabase?.auth.signOut() ?? Promise.resolve()).finally(() => {
      signingOut.current = false
    })
  }, [supabase])

  const getToken = useCallback(async () => {
    if (!supabase) return null
    const { data } = await supabase.auth.getSession()
    return data.session?.access_token ?? null
  }, [supabase])

  const value = useMemo<AuthValue>(
    () => ({
      status,
      email,
      expired,
      configured: supabase !== null,
      signIn,
      signOut,
      handleUnauthorized,
      getToken,
    }),
    [status, email, expired, supabase, signIn, signOut, handleUnauthorized, getToken],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
