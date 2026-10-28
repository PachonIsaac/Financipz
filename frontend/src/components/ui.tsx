import {
  useId,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react'

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost'

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-emerald-500 text-slate-950 font-semibold active:bg-emerald-400 disabled:bg-emerald-500/40',
  secondary:
    'bg-slate-200 text-slate-900 dark:bg-slate-800 dark:text-slate-100 active:bg-slate-300 dark:active:bg-slate-700',
  danger: 'bg-red-600 text-white font-semibold active:bg-red-500 disabled:bg-red-600/40',
  ghost: 'bg-transparent text-emerald-700 dark:text-emerald-400 active:bg-slate-200/60 dark:active:bg-slate-800',
}

export function Button({
  variant = 'primary',
  className = '',
  type = 'button',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type={type}
      className={`inline-flex min-h-11 items-center justify-center rounded-xl px-4 text-base disabled:cursor-not-allowed ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  )
}

const CONTROL =
  'min-h-11 w-full rounded-xl border border-slate-300 bg-white px-3 text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100'

interface FieldShellProps {
  label: string
  error?: string | undefined
  hint?: string | undefined
}

function FieldShell({
  label,
  error,
  hint,
  id,
  children,
}: FieldShellProps & { id: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-slate-600 dark:text-slate-300">
        {label}
      </label>
      {children}
      {hint && !error ? <p className="text-xs text-slate-500 dark:text-slate-400">{hint}</p> : null}
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      ) : null}
    </div>
  )
}

export function TextField({
  label,
  error,
  hint,
  className = '',
  ...props
}: FieldShellProps & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId()
  return (
    <FieldShell label={label} error={error} hint={hint} id={id}>
      <input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        className={`${CONTROL} ${className}`}
        {...props}
      />
    </FieldShell>
  )
}

export function TextAreaField({
  label,
  error,
  hint,
  ...props
}: FieldShellProps & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const id = useId()
  return (
    <FieldShell label={label} error={error} hint={hint} id={id}>
      <textarea
        id={id}
        rows={2}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        className={`${CONTROL} py-2`}
        {...props}
      />
    </FieldShell>
  )
}

export function SelectField({
  label,
  error,
  hint,
  children,
  ...props
}: FieldShellProps & SelectHTMLAttributes<HTMLSelectElement>) {
  const id = useId()
  return (
    <FieldShell label={label} error={error} hint={hint} id={id}>
      <select
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        className={CONTROL}
        {...props}
      >
        {children}
      </select>
    </FieldShell>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <section
      className={`rounded-3xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900 ${className}`}
    >
      {children}
    </section>
  )
}

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'warning' }) {
  const tones = {
    neutral: 'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
    warning: 'bg-amber-200 text-amber-900 dark:bg-amber-900/50 dark:text-amber-200',
  }
  return <span className={`rounded-md px-1.5 py-0.5 text-xs font-medium ${tones[tone]}`}>{children}</span>
}
