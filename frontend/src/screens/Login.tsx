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
    <div className="mx-auto flex min-h-dvh max-w-sm flex-col justify-center gap-6 px-6 pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)]">
      <div className="flex flex-col items-center gap-2">
        <img src={`${import.meta.env.BASE_URL}icon.svg`} alt="" className="size-16" />
        <h1 className="text-3xl font-bold">Financipz</h1>
      </div>
      {auth.expired ? (
        <p role="status" className="rounded-xl bg-amber-100 p-3 text-sm text-amber-900">
          Tu sesión expiró. Inicia sesión de nuevo.
        </p>
      ) : null}
      {!auth.configured ? (
        <p role="alert" className="rounded-xl bg-red-100 p-3 text-sm text-red-800">
          Falta configurar el inicio de sesión de la aplicación.
        </p>
      ) : null}
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
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
