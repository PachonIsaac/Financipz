import { useState, type FormEvent } from 'react'
import { useAuth } from '../auth/AuthProvider'
import { Button, TextField } from '../components/ui'

export function LoginScreen() {
  const auth = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!email.trim() || !password) {
      setError('Escribe tu correo y tu contraseña.')
      return
    }
    setPending(true)
    setError(null)
    const message = await auth.signIn(email.trim(), password)
    setPending(false)
    if (message) setError(message)
  }

  return (
    <div className="relative mx-auto flex min-h-dvh max-w-sm flex-col justify-center gap-8 overflow-hidden px-6 pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)]">
      <div aria-hidden="true" className="pointer-events-none absolute -top-20 left-1/2 size-80 -translate-x-1/2 rounded-full bg-emerald-500/20 blur-[70px]" />
      <div className="relative flex flex-col items-center gap-3 text-center">
        <span className="flex size-[84px] items-center justify-center rounded-3xl border border-slate-800 bg-slate-900">
          <img src={`${import.meta.env.BASE_URL}icon.svg`} alt="" className="size-12" />
        </span>
        <h1 className="text-[34px] leading-10 font-bold tracking-tight">Financipz</h1>
        <p className="text-base text-slate-400">Tus finanzas personales, en un solo lugar.</p>
      </div>
      {auth.expired ? (
        <p role="status" className="relative rounded-xl bg-amber-200 p-3 text-sm text-amber-900">
          Tu sesión expiró. Inicia sesión de nuevo.
        </p>
      ) : null}
      {!auth.configured ? (
        <p role="alert" className="relative rounded-xl bg-red-100 p-3 text-sm text-red-800">
          Falta configurar el inicio de sesión de la aplicación.
        </p>
      ) : null}
      <form onSubmit={handleSubmit} noValidate className="relative flex flex-col gap-4">
        <TextField
          label="Correo electrónico"
          type="email"
          autoComplete="username"
          inputMode="email"
          autoCapitalize="none"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <TextField
          label="Contraseña"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error ? (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {error}
          </p>
        ) : null}
        <Button type="submit" disabled={pending}>
          {pending ? 'Entrando…' : 'Iniciar sesión'}
        </Button>
      </form>
    </div>
  )
}
