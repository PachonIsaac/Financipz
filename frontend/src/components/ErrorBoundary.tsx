import { Component, type ErrorInfo, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'

interface Props {
  children: ReactNode
  /** What the user reads when this part could not be shown. */
  label?: string
  /** Show nothing at all when this part fails, for details the screen can do without. */
  quiet?: boolean
}

interface State {
  failed: boolean
}

/**
 * Stops a failure while drawing one part of the screen from taking the whole app down. Without it,
 * React removes everything and the user is left with a blank page.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false }

  static getDerivedStateFromError(): State {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Could not draw part of the screen', error, info.componentStack)
  }

  render(): ReactNode {
    if (!this.state.failed) return this.props.children
    if (this.props.quiet) return null
    return (
      <div role="alert" className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100">
        <p>{this.props.label ?? 'No se pudo mostrar esta sección.'}</p>
        <button
          type="button"
          onClick={() => this.setState({ failed: false })}
          className="mt-2 inline-flex min-h-11 items-center font-medium underline"
        >
          Reintentar
        </button>
      </div>
    )
  }
}

/** Wraps a whole screen. Moving to another route starts fresh, so one broken screen never sticks. */
export function RouteErrorBoundary({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()
  return (
    <ErrorBoundary key={pathname} label="No se pudo mostrar esta pantalla. Intenta de nuevo o vuelve al inicio.">
      {children}
    </ErrorBoundary>
  )
}
