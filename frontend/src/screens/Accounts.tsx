import { useState, type FormEvent } from 'react'
import {
  useAccounts,
  useAdjustAccount,
  useCreateAccount,
  useIdentifiers,
  useReplaceIdentifiers,
  useUpdateAccount,
} from '../api/hooks'
import type { Account, Currency, Identifier, IdentifierType } from '../api/types'
import { Amount } from '../components/Amount'
import { PageHeader } from '../components/Layout'
import { EmptyState, ErrorState, FormError, ListSkeleton } from '../components/states'
import { useToast } from '../components/Toast'
import { Badge, Button, Card, SelectField, TextField } from '../components/ui'
import {
  accountToValues,
  buildAccountCreate,
  buildAccountUpdate,
  emptyAccountValues,
  validateAccountForm,
  validateIdentifiers,
  type AccountFormErrors,
  type AccountFormValues,
} from '../features/accounts/form'
import { ACCOUNT_TYPE_LABELS, IDENTIFIER_TYPE_LABELS, SELECTABLE_ACCOUNT_TYPES } from '../features/labels'
import { parseAmountInput } from '../lib/money'

type Panel =
  | { kind: 'list' }
  | { kind: 'create' }
  | { kind: 'edit'; account: Account }
  | { kind: 'adjust'; account: Account }

function AccountForm({ account, onDone }: { account?: Account; onDone: () => void }) {
  const toast = useToast()
  const create = useCreateAccount()
  const update = useUpdateAccount()
  const [values, setValues] = useState<AccountFormValues>(account ? accountToValues(account) : emptyAccountValues())
  const [errors, setErrors] = useState<AccountFormErrors>({})
  const mutation = account ? update : create
  const set = <K extends keyof AccountFormValues>(key: K, value: AccountFormValues[K]) =>
    setValues((current) => ({ ...current, [key]: value }))

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const { errors: found, parsed } = validateAccountForm(values)
    setErrors(found)
    if (!parsed) return
    if (account) {
      const body = buildAccountUpdate(parsed, account)
      if (Object.keys(body).length === 0) return onDone()
      update.mutate(
        { id: account.id, body },
        {
          onSuccess: () => {
            toast.show('Cuenta actualizada')
            onDone()
          },
        },
      )
    } else {
      create.mutate(buildAccountCreate(parsed), {
        onSuccess: () => {
          toast.show('Cuenta creada')
          onDone()
        },
      })
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <TextField label="Nombre" value={values.name} onChange={(e) => set('name', e.target.value)} error={errors.name} />
      <SelectField
        label="Tipo de cuenta"
        value={values.type}
        onChange={(e) => set('type', e.target.value as Account['type'])}
      >
        {SELECTABLE_ACCOUNT_TYPES.map((type) => (
          <option key={type} value={type}>
            {ACCOUNT_TYPE_LABELS[type]}
          </option>
        ))}
      </SelectField>
      <SelectField
        label="Moneda"
        value={values.currency}
        disabled={account !== undefined}
        hint={account ? 'La moneda no se puede cambiar.' : undefined}
        onChange={(e) => set('currency', e.target.value as Currency)}
      >
        <option value="COP">COP (pesos)</option>
        <option value="USD">USD (dólares)</option>
      </SelectField>
      <TextField
        label="Saldo inicial"
        inputMode="decimal"
        placeholder="0"
        value={values.initialBalance}
        onChange={(e) => set('initialBalance', e.target.value)}
        error={errors.initialBalance}
      />
      {values.type === 'loan' ? (
        <TextField
          label="Persona a quien le prestaste"
          value={values.counterparty}
          onChange={(e) => set('counterparty', e.target.value)}
          error={errors.counterparty}
        />
      ) : null}
      <TextField
        label="Llave Bre-b (opcional)"
        autoCapitalize="none"
        autoCorrect="off"
        value={values.key}
        onChange={(e) => set('key', e.target.value)}
        error={errors.key}
      />
      {account?.type === 'exchange' ? null : (
        <label className="flex min-h-11 items-start gap-3">
          <input
            type="checkbox"
            className="mt-0.5 size-5"
            checked={values.includeInBalance}
            onChange={(e) => set('includeInBalance', e.target.checked)}
          />
          <span>
            <span className="block text-base">Incluir en el balance</span>
            <span className="block text-sm text-slate-600 dark:text-slate-400">
              Si lo desactivas, esta cuenta no suma al disponible, a la deuda de tarjetas ni a los préstamos.
            </span>
          </span>
        </label>
      )}
      <FormError error={mutation.error} />
      <Button type="submit" disabled={mutation.isPending}>
        {mutation.isPending ? 'Guardando…' : account ? 'Guardar cambios' : 'Crear cuenta'}
      </Button>
    </form>
  )
}

function IdentifiersEditor({ accountId }: { accountId: string }) {
  const toast = useToast()
  const query = useIdentifiers(accountId)
  const save = useReplaceIdentifiers()
  const [draft, setDraft] = useState<Identifier[] | null>(null)
  const [problem, setProblem] = useState<string | null>(null)

  if (query.isPending) return <ListSkeleton rows={1} label="Cargando los identificadores" />
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />

  const items = draft ?? query.data
  const change = (next: Identifier[]) => {
    setDraft(next)
    setProblem(null)
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-slate-600 dark:text-slate-400">
        Últimos 4 dígitos con los que aparece esta cuenta o tarjeta en las notificaciones.
      </p>
      {items.map((item, index) => (
        <div key={index} className="flex items-end gap-2">
          <div className="w-28">
            <TextField
              label={`Dígitos ${index + 1}`}
              inputMode="numeric"
              maxLength={4}
              value={item.digits}
              onChange={(e) =>
                change(items.map((it, i) => (i === index ? { ...it, digits: e.target.value.replace(/\D/g, '') } : it)))
              }
            />
          </div>
          <div className="min-w-0 flex-1">
            <SelectField
              label={`Tipo ${index + 1}`}
              value={item.type}
              onChange={(e) =>
                change(items.map((it, i) => (i === index ? { ...it, type: e.target.value as IdentifierType } : it)))
              }
            >
              {(Object.keys(IDENTIFIER_TYPE_LABELS) as IdentifierType[]).map((type) => (
                <option key={type} value={type}>
                  {IDENTIFIER_TYPE_LABELS[type]}
                </option>
              ))}
            </SelectField>
          </div>
          <Button
            variant="secondary"
            aria-label={`Quitar identificador ${index + 1}`}
            onClick={() => change(items.filter((_, i) => i !== index))}
          >
            ×
          </Button>
        </div>
      ))}
      {problem ? (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {problem}
        </p>
      ) : null}
      <FormError error={save.error} />
      <div className="grid grid-cols-2 gap-2">
        <Button variant="secondary" onClick={() => change([...items, { digits: '', type: 'account' }])}>
          Agregar
        </Button>
        <Button
          disabled={draft === null || save.isPending}
          onClick={() => {
            const message = validateIdentifiers(items)
            if (message) return setProblem(message)
            save.mutate(
              { id: accountId, identifiers: items },
              {
                onSuccess: () => {
                  setDraft(null)
                  toast.show('Identificadores guardados')
                },
              },
            )
          }}
        >
          {save.isPending ? 'Guardando…' : 'Guardar'}
        </Button>
      </div>
    </div>
  )
}

function AdjustForm({ account, onDone }: { account: Account; onDone: () => void }) {
  const toast = useToast()
  const adjust = useAdjustAccount()
  const [balance, setBalance] = useState('')
  const [note, setNote] = useState('')
  const [errors, setErrors] = useState<{ balance?: string; note?: string }>({})

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const parsed = parseAmountInput(balance, { allowNegative: true })
    const found: typeof errors = {}
    if (parsed === null) found.balance = 'Escribe el saldo que ves en la cuenta.'
    if (!note.trim()) found.note = 'Escribe el motivo del ajuste.'
    setErrors(found)
    if (parsed === null || found.note) return
    adjust.mutate(
      { id: account.id, body: { observed_balance: parsed, note: note.trim() } },
      {
        onSuccess: (result) => {
          toast.show(result.transaction ? 'Saldo ajustado' : 'El saldo ya coincidía')
          onDone()
        },
      },
    )
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <p className="text-sm text-slate-600 dark:text-slate-400">
        Saldo actual: <Amount value={account.balance} currency={account.currency} exact />. Escribe el saldo real y
        se registrará un movimiento de ajuste por la diferencia.
      </p>
      <TextField
        label={`Saldo real (${account.currency})`}
        inputMode="decimal"
        value={balance}
        onChange={(e) => setBalance(e.target.value)}
        error={errors.balance}
      />
      <TextField label="Motivo" value={note} onChange={(e) => setNote(e.target.value)} error={errors.note} />
      <FormError error={adjust.error} />
      <Button type="submit" disabled={adjust.isPending}>
        {adjust.isPending ? 'Guardando…' : 'Ajustar saldo'}
      </Button>
    </form>
  )
}

function EditPanel({ account, onNavigate }: { account: Account; onNavigate: (panel: Panel) => void }) {
  const toast = useToast()
  const update = useUpdateAccount()
  return (
    <div className="flex flex-col gap-6">
      <AccountForm account={account} onDone={() => onNavigate({ kind: 'list' })} />
      <Card>
        <h2 className="mb-2 text-base font-semibold">Identificadores</h2>
        <IdentifiersEditor accountId={account.id} />
      </Card>
      <div className="grid grid-cols-2 gap-2">
        <Button variant="secondary" onClick={() => onNavigate({ kind: 'adjust', account })}>
          Ajustar saldo
        </Button>
        <Button
          variant={account.archived ? 'secondary' : 'danger'}
          disabled={update.isPending}
          onClick={() =>
            update.mutate(
              { id: account.id, body: { archived: !account.archived } },
              {
                onSuccess: () => {
                  toast.show(account.archived ? 'Cuenta restaurada' : 'Cuenta archivada')
                  onNavigate({ kind: 'list' })
                },
              },
            )
          }
        >
          {account.archived ? 'Restaurar' : 'Archivar'}
        </Button>
      </div>
      <FormError error={update.error} />
    </div>
  )
}

export function AccountsScreen() {
  const accounts = useAccounts()
  const [panel, setPanel] = useState<Panel>({ kind: 'list' })
  const [showArchived, setShowArchived] = useState(false)
  const toList = () => setPanel({ kind: 'list' })

  if (panel.kind === 'create') {
    return (
      <>
        <PageHeader title="Nueva cuenta" action={<Button variant="ghost" onClick={toList}>Cancelar</Button>} />
        <AccountForm onDone={toList} />
      </>
    )
  }
  if (panel.kind === 'edit') {
    return (
      <>
        <PageHeader title="Editar cuenta" action={<Button variant="ghost" onClick={toList}>Cancelar</Button>} />
        <EditPanel account={panel.account} onNavigate={setPanel} />
      </>
    )
  }
  if (panel.kind === 'adjust') {
    return (
      <>
        <PageHeader
          title="Ajustar saldo"
          action={<Button variant="ghost" onClick={() => setPanel({ kind: 'edit', account: panel.account })}>Cancelar</Button>}
        />
        <AdjustForm account={panel.account} onDone={toList} />
      </>
    )
  }

  const all = accounts.data ?? []
  const visible = all.filter((a) => showArchived || !a.archived)
  const hasArchived = all.some((a) => a.archived)

  return (
    <>
      <PageHeader
        title="Cuentas"
        back={{ to: '/more', label: 'Volver a Más' }}
        action={<Button onClick={() => setPanel({ kind: 'create' })}>Nueva</Button>}
      />
      {accounts.isPending ? (
        <ListSkeleton rows={4} label="Cargando las cuentas" />
      ) : accounts.isError ? (
        <ErrorState error={accounts.error} onRetry={() => void accounts.refetch()} />
      ) : visible.length === 0 ? (
        <EmptyState
          title="Aún no tienes cuentas"
          description="Crea una para empezar a registrar movimientos."
          action={<Button onClick={() => setPanel({ kind: 'create' })}>Crear cuenta</Button>}
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {visible.map((account) => (
            <li key={account.id}>
              <button
                type="button"
                onClick={() => setPanel({ kind: 'edit', account })}
                className="flex min-h-14 w-full items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-2 text-left active:bg-slate-100 dark:border-slate-800 dark:bg-slate-900 dark:active:bg-slate-800"
              >
                <span className="min-w-0">
                  <span className="block truncate text-base font-medium">{account.name}</span>
                  <span className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400">
                    {ACCOUNT_TYPE_LABELS[account.type]} · {account.currency}
                    {account.archived ? <Badge>Archivada</Badge> : null}
                    {account.include_in_balance ? null : <Badge>Fuera del balance</Badge>}
                  </span>
                </span>
                <Amount value={account.balance} currency={account.currency} className="text-base font-semibold" />
              </button>
            </li>
          ))}
        </ul>
      )}
      {hasArchived ? (
        <label className="mt-4 flex min-h-11 items-center gap-3 text-sm">
          <input
            type="checkbox"
            className="size-5"
            checked={showArchived}
            onChange={(e) => setShowArchived(e.target.checked)}
          />
          Mostrar cuentas archivadas
        </label>
      ) : null}
    </>
  )
}
