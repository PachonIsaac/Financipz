import { useState, type FormEvent } from 'react'
import { PiggyBank } from 'lucide-react'
import {
  useAccounts,
  useCategories,
  useCreateEnvelope,
  useDeleteEnvelope,
  useEnvelopeEntry,
  useEnvelopes,
  usePayWithEnvelope,
  useUpdateEnvelope,
} from '../api/hooks'
import type { Envelope } from '../api/types'
import { Amount } from '../components/Amount'
import { PageHeader } from '../components/Layout'
import { EmptyState, ErrorState, FormError, ListSkeleton } from '../components/states'
import { useToast } from '../components/Toast'
import { Badge, Button, Card, SelectField, Switch, TextField } from '../components/ui'
import { IconChip } from '../features/appearance'
import { suggestedMonthly } from '../features/envelopes/suggest'
import { categoryOptions } from '../features/transactions/display'
import { formatDate, todayLocal } from '../lib/dates'
import { fromCents, parseAmountInput, toCents } from '../lib/money'

type Panel =
  | { kind: 'list' }
  | { kind: 'form'; envelope?: Envelope }
  | { kind: 'move'; envelope: Envelope; mode: 'contribute' | 'release' }
  | { kind: 'pay'; envelope: Envelope }

// Only the accounts the person spends from can hold an envelope.
const SPENDING_TYPES = ['cash', 'bank', 'savings', 'wallet']

function progressOf(envelope: Envelope): number {
  if (!envelope.target_amount) return 0
  const target = toCents(envelope.target_amount)
  if (target <= 0n) return 0
  const held = toCents(envelope.balance)
  return Number(held >= target ? 100n : (held * 100n) / target)
}

function EnvelopeForm({ envelope, onDone }: { envelope?: Envelope; onDone: () => void }) {
  const toast = useToast()
  const accounts = useAccounts()
  const create = useCreateEnvelope()
  const update = useUpdateEnvelope()
  const remove = useDeleteEnvelope()
  const [name, setName] = useState(envelope?.name ?? '')
  const [accountId, setAccountId] = useState(envelope?.account_id ?? '')
  const [target, setTarget] = useState(envelope?.target_amount ? envelope.target_amount.replace('.', ',') : '')
  const [due, setDue] = useState(envelope?.due_date ?? '')
  const [repeats, setRepeats] = useState(envelope?.repeats_yearly ?? false)
  const [errors, setErrors] = useState<{ name?: string; account?: string; target?: string }>({})
  const options = (accounts.data ?? []).filter((a) => !a.archived && SPENDING_TYPES.includes(a.type))
  const mutation = envelope ? update : create

  const parsedTarget = target.trim() === '' ? null : parseAmountInput(target)
  const currency = envelope?.currency ?? options.find((a) => a.id === accountId)?.currency ?? 'COP'
  const suggestion =
    parsedTarget && due ? suggestedMonthly(parsedTarget, envelope?.balance ?? '0.00', due, todayLocal()) : null

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const found: typeof errors = {}
    if (!name.trim()) found.name = 'Escribe un nombre.'
    if (!envelope && !accountId) found.account = 'Elige la cuenta donde está la plata.'
    if (target.trim() !== '' && (parsedTarget === null || toCents(parsedTarget) <= 0n)) {
      found.target = 'Escribe un monto válido.'
    }
    setErrors(found)
    if (Object.keys(found).length > 0) return
    const common = { name: name.trim(), target_amount: parsedTarget, due_date: due || null, repeats_yearly: repeats }
    if (envelope) {
      update.mutate(
        { id: envelope.id, body: common },
        { onSuccess: () => { toast.show('Cajita actualizada'); onDone() } },
      )
    } else {
      create.mutate(
        { account_id: accountId, ...common },
        { onSuccess: () => { toast.show('Cajita creada'); onDone() } },
      )
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <p className="text-sm text-slate-400">
        Una cajita aparta plata dentro de una cuenta para un pago que ya sabes que viene. No cuenta en tu balance.
      </p>
      <TextField label="Nombre" value={name} onChange={(e) => setName(e.target.value)} error={errors.name} />
      {envelope ? null : (
        <SelectField
          label="Cuenta donde está la plata"
          value={accountId}
          onChange={(e) => setAccountId(e.target.value)}
          error={errors.account}
        >
          <option value="">Elige la cuenta</option>
          {options.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </SelectField>
      )}
      <TextField
        label="Monto aproximado del pago"
        inputMode="decimal"
        value={target}
        onChange={(e) => setTarget(e.target.value)}
        error={errors.target}
      />
      <TextField label="Fecha del pago" type="date" value={due} onChange={(e) => setDue(e.target.value)} />
      <Card>
        <Switch
          checked={repeats}
          onChange={setRepeats}
          label="Se repite cada año"
          description="Encendido: al pagar, la fecha pasa un año adelante y el monto se conserva."
        />
      </Card>
      {suggestion !== null ? (
        <div role="status" className="rounded-3xl border border-orange-400/35 bg-orange-400/10 p-4">
          <p className="text-sm text-slate-400">Para llegar a la fecha</p>
          <p className="text-[28px] leading-[34px] font-bold text-orange-400">
            <Amount value={fromCents(suggestion)} currency={currency} tone="neutral" />{' '}
            <span className="text-base font-medium text-slate-100">al mes</span>
          </p>
        </div>
      ) : null}
      <FormError error={mutation.error ?? remove.error} />
      <Button type="submit" disabled={mutation.isPending}>
        {mutation.isPending ? 'Guardando…' : envelope ? 'Guardar cambios' : 'Crear cajita'}
      </Button>
      {envelope ? (
        <Button
          variant="danger"
          disabled={remove.isPending}
          onClick={() => remove.mutate(envelope.id, { onSuccess: () => { toast.show('Cajita borrada'); onDone() } })}
        >
          Borrar cajita
        </Button>
      ) : null}
    </form>
  )
}

function MoveForm({ envelope, mode, onDone }: { envelope: Envelope; mode: 'contribute' | 'release'; onDone: () => void }) {
  const toast = useToast()
  const entry = useEnvelopeEntry()
  const accounts = useAccounts()
  const account = (accounts.data ?? []).find((a) => a.id === envelope.account_id)
  const [amount, setAmount] = useState('')
  const [error, setError] = useState<string | undefined>()
  const parsed = parseAmountInput(amount)
  const suggested = envelope.suggested_monthly && toCents(envelope.suggested_monthly) > 0n ? envelope.suggested_monthly : null
  const available = account ? toCents(account.balance) - toCents(account.reserved) : null
  const after = parsed ? toCents(envelope.balance) + (mode === 'contribute' ? 1n : -1n) * toCents(parsed) : null

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (parsed === null || toCents(parsed) <= 0n) return setError('Escribe un monto mayor que cero.')
    setError(undefined)
    entry.mutate(
      { id: envelope.id, kind: mode, amount: parsed },
      { onSuccess: () => { toast.show(mode === 'contribute' ? 'Plata apartada' : 'Plata liberada'); onDone() } },
    )
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <TextField label="Monto" inputMode="decimal" autoFocus value={amount} onChange={(e) => setAmount(e.target.value)} error={error} />
      {mode === 'contribute' && suggested ? (
        <Button variant="secondary" onClick={() => setAmount(suggested.replace('.', ','))}>
          Usar el sugerido: <Amount value={suggested} currency={envelope.currency} tone="neutral" className="ml-1" />
        </Button>
      ) : null}
      <Card className="flex flex-col gap-1.5 text-sm">
        {mode === 'contribute' && available !== null ? (
          <p className="flex justify-between">
            <span className="text-slate-400">Disponible en {envelope.account_name}</span>
            <Amount value={fromCents(available)} currency={envelope.currency} tone="neutral" />
          </p>
        ) : null}
        <p className="flex justify-between">
          <span className="text-slate-400">Ya apartado en esta cajita</span>
          <Amount value={envelope.balance} currency={envelope.currency} tone="neutral" />
        </p>
        {after !== null && after >= 0n ? (
          <p className="flex justify-between border-t border-slate-800 pt-2">
            <span className="text-slate-400">Quedará apartado</span>
            <Amount value={fromCents(after)} currency={envelope.currency} tone="neutral" className="font-bold text-orange-400" />
          </p>
        ) : null}
      </Card>
      <p className="text-[13px] leading-[19px] text-slate-400">
        {mode === 'contribute'
          ? 'Aportar no es un gasto: el saldo de la cuenta no cambia, solo baja lo que cuenta en tu balance.'
          : 'Liberar devuelve la plata a lo disponible de la cuenta.'}
      </p>
      <FormError error={entry.error} />
      <Button type="submit" disabled={entry.isPending}>
        {entry.isPending ? 'Guardando…' : mode === 'contribute' ? 'Aportar' : 'Liberar'}
      </Button>
    </form>
  )
}

function PayForm({ envelope, onDone }: { envelope: Envelope; onDone: () => void }) {
  const toast = useToast()
  const pay = usePayWithEnvelope()
  const accounts = useAccounts()
  const categories = useCategories('expense')
  const [amount, setAmount] = useState((envelope.target_amount ?? envelope.balance).replace('.00', '').replace('.', ','))
  const [categoryId, setCategoryId] = useState('')
  const [merchant, setMerchant] = useState(envelope.name)
  const [error, setError] = useState<string | undefined>()
  const parsed = parseAmountInput(amount)
  const options = (accounts.data ?? []).filter(
    (a) => !a.archived && a.currency === envelope.currency && !['exchange', 'system', 'loan'].includes(a.type),
  )
  // The envelope's own account may have been archived since: then the first valid one is the default.
  const [chosenAccount, setAccountId] = useState(envelope.account_id)
  const accountId = options.some((a) => a.id === chosenAccount) ? chosenAccount : (options[0]?.id ?? '')
  const payingAccount = options.find((a) => a.id === accountId)
  const left =
    parsed && toCents(parsed) <= toCents(envelope.balance) ? toCents(envelope.balance) - toCents(parsed) : 0n

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (parsed === null || toCents(parsed) <= 0n) return setError('Escribe el monto del pago.')
    setError(undefined)
    pay.mutate(
      {
        id: envelope.id,
        body: {
          expense: {
            account_id: accountId,
            amount: parsed,
            category_id: categoryId || null,
            merchant: merchant.trim() || null,
          },
        },
      },
      { onSuccess: () => { toast.show('Pago registrado'); onDone() } },
    )
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <TextField label="Monto del pago" inputMode="decimal" autoFocus value={amount} onChange={(e) => setAmount(e.target.value)} error={error} />
      <SelectField label="Con qué se paga (cuenta del gasto)" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
        {options.map((a) => (
          <option key={a.id} value={a.id}>
            {a.name}
          </option>
        ))}
      </SelectField>
      <SelectField label="Categoría" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
        <option value="">Sin categoría</option>
        {categoryOptions(categories.data ?? [], 'expense').map((o) => (
          <option key={o.id} value={o.id}>
            {o.label}
          </option>
        ))}
      </SelectField>
      <TextField label="Comercio o nota" value={merchant} onChange={(e) => setMerchant(e.target.value)} />
      <div className="rounded-2xl border border-orange-400/35 bg-orange-400/10 p-4 text-sm">
        <p className="mb-1.5 font-semibold">Qué va a pasar</p>
        <ul className="list-disc pl-5 text-slate-300">
          <li>Se registra un gasto{parsed ? <> de <Amount value={parsed} currency={envelope.currency} tone="neutral" /></> : null}{payingAccount ? ` en ${payingAccount.name}` : ''}, este mes y con su categoría.</li>
          <li>
            La cajita queda en <Amount value={fromCents(left)} currency={envelope.currency} tone="neutral" />. Si pagas más de lo que tiene, la diferencia sale de lo disponible.
          </li>
        </ul>
      </div>
      <FormError error={pay.error} />
      <Button type="submit" disabled={pay.isPending}>
        {pay.isPending ? 'Pagando…' : 'Pagar con la cajita'}
      </Button>
    </form>
  )
}

function EnvelopeCard({ envelope, onPanel }: { envelope: Envelope; onPanel: (panel: Panel) => void }) {
  const percent = progressOf(envelope)
  const suggestion = envelope.suggested_monthly
  const shortfall = toCents(envelope.shortfall) > 0n
  return (
    <Card className={envelope.ready ? 'border-emerald-400/40' : ''}>
      <button
        type="button"
        onClick={() => onPanel({ kind: 'form', envelope })}
        className="flex min-h-11 w-full items-center gap-3 text-left"
        aria-label={`Editar ${envelope.name}`}
      >
        <IconChip icon={PiggyBank} />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[17px] font-semibold">{envelope.name}</span>
          <span className="block text-[13px] text-slate-400">
            En {envelope.account_name}
            {envelope.due_date ? ` · pago ${formatDate(envelope.due_date)}` : ''}
            {envelope.repeats_yearly ? ' · se repite' : ''}
          </span>
        </span>
        {envelope.ready ? (
          <Badge>Lista</Badge>
        ) : envelope.months_left !== null ? (
          <span className="text-[13px] text-slate-400">{envelope.months_left} {envelope.months_left === 1 ? 'mes' : 'meses'}</span>
        ) : null}
      </button>
      <div className="mt-3 flex items-baseline justify-between">
        <Amount value={envelope.balance} currency={envelope.currency} tone="neutral" className="text-[22px] font-bold" />
        {envelope.target_amount ? (
          <span className="text-[13px] text-slate-400">
            de <Amount value={envelope.target_amount} currency={envelope.currency} tone="neutral" />
          </span>
        ) : null}
      </div>
      {envelope.target_amount ? (
        <div
          role="progressbar"
          aria-label={`Progreso de ${envelope.name}`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          className="mt-2 h-2 rounded-full bg-slate-950"
        >
          <div className={`h-2 rounded-full ${envelope.ready ? 'bg-emerald-400' : 'bg-orange-400'}`} style={{ width: `${percent}%` }} />
        </div>
      ) : null}
      {suggestion !== null && !envelope.ready ? (
        <p className="mt-2.5 text-[13px] text-slate-400">
          Sugerido este mes: <Amount value={suggestion} currency={envelope.currency} tone="neutral" className="font-semibold text-slate-100" />
        </p>
      ) : null}
      {shortfall ? (
        <p role="alert" className="mt-2.5 rounded-xl border border-amber-400/35 bg-amber-400/10 p-2.5 text-[13px] text-amber-200">
          Apartaste más de lo que hay en la cuenta.
        </p>
      ) : null}
      <div className="mt-3 grid grid-cols-3 gap-2">
        <Button variant={envelope.ready ? 'secondary' : 'primary'} onClick={() => onPanel({ kind: 'move', envelope, mode: 'contribute' })}>
          Aportar
        </Button>
        <Button variant={envelope.ready ? 'primary' : 'secondary'} onClick={() => onPanel({ kind: 'pay', envelope })}>
          Pagar
        </Button>
        <Button variant="secondary" onClick={() => onPanel({ kind: 'move', envelope, mode: 'release' })}>
          Liberar
        </Button>
      </div>
    </Card>
  )
}

export function EnvelopesScreen() {
  const list = useEnvelopes()
  const [panel, setPanel] = useState<Panel>({ kind: 'list' })
  const toList = () => setPanel({ kind: 'list' })
  const cancel = <Button variant="ghost" onClick={toList}>Cancelar</Button>

  if (panel.kind === 'form') {
    return (
      <>
        <PageHeader title={panel.envelope ? 'Editar cajita' : 'Nueva cajita'} action={cancel} />
        <EnvelopeForm envelope={panel.envelope} onDone={toList} />
      </>
    )
  }
  if (panel.kind === 'move') {
    return (
      <>
        <PageHeader title={`${panel.mode === 'contribute' ? 'Aportar a' : 'Liberar de'} «${panel.envelope.name}»`} action={cancel} />
        <MoveForm envelope={panel.envelope} mode={panel.mode} onDone={toList} />
      </>
    )
  }
  if (panel.kind === 'pay') {
    return (
      <>
        <PageHeader title={`Pagar con «${panel.envelope.name}»`} action={cancel} />
        <PayForm envelope={panel.envelope} onDone={toList} />
      </>
    )
  }

  const data = list.data
  return (
    <>
      <PageHeader
        title="Cajitas"
        back={{ to: '/more', label: 'Volver a Más' }}
        action={<Button onClick={() => setPanel({ kind: 'form' })}>Nueva</Button>}
      />
      {list.isPending ? (
        <ListSkeleton rows={3} label="Cargando las cajitas" />
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => void list.refetch()} />
      ) : !data || data.envelopes.length === 0 ? (
        <EmptyState
          title="Aún no tienes cajitas"
          description="Aparta plata dentro de una cuenta para un pago que ya sabes que viene."
          action={<Button onClick={() => setPanel({ kind: 'form' })}>Crear cajita</Button>}
        />
      ) : (
        <div className="flex flex-col gap-4">
          <Card>
            <p className="text-sm font-medium text-slate-400">Apartado en cajitas</p>
            <p className="text-[40px] leading-[46px] font-bold tracking-tight">
              <Amount value={data.reserved_total} currency="COP" tone="neutral" />
            </p>
            <p className="mt-1.5 text-[13px] leading-[19px] text-slate-400">
              No cuenta en tu balance. Está dentro de tus cuentas, separado de lo que gastas cada mes.
            </p>
            <div className="mt-3.5 flex items-center justify-between gap-3 rounded-2xl bg-orange-400/10 px-3.5 py-3">
              <span className="text-sm">Aporte sugerido de este mes</span>
              <Amount value={data.suggested_total} currency="COP" tone="neutral" className="text-[17px] font-bold text-orange-400" />
            </div>
          </Card>
          {data.envelopes.map((envelope) => (
            <EnvelopeCard key={envelope.id} envelope={envelope} onPanel={setPanel} />
          ))}
        </div>
      )}
    </>
  )
}
