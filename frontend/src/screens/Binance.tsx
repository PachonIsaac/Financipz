import { useState, type FormEvent } from 'react'
import { useConnectBinance, useDisconnectBinance, useIntegrations, useSyncBinance } from '../api/hooks'
import type { Integration } from '../api/types'
import { PageHeader } from '../components/Layout'
import { ErrorState, FormError, ListSkeleton } from '../components/states'
import { useToast } from '../components/Toast'
import { Button, Card, TextField } from '../components/ui'
import { formatDateTime } from '../lib/dates'

const STATUS: Record<Integration['status'], { label: string; dot: string; chip: string }> = {
  active: { label: 'Conectada', dot: 'bg-income', chip: 'bg-income/15 text-income' },
  error: { label: 'Con problemas', dot: 'bg-amber-400', chip: 'bg-amber-400/15 text-amber-300' },
  disconnected: { label: 'Sin conectar', dot: 'bg-slate-500', chip: 'bg-slate-800 text-slate-400' },
}

function StatusChip({ status }: { status: Integration['status'] }) {
  const look = STATUS[status]
  return (
    <span className={`inline-flex min-h-7 items-center gap-1.5 rounded-full px-3 text-[13px] font-semibold ${look.chip}`}>
      <span aria-hidden="true" className={`size-2 rounded-full ${look.dot}`} />
      {look.label}
    </span>
  )
}

function ConnectForm() {
  const toast = useToast()
  const connect = useConnectBinance()
  const [apiKey, setApiKey] = useState('')
  const [apiSecret, setApiSecret] = useState('')
  const [problem, setProblem] = useState<string | null>(null)

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!apiKey.trim() || !apiSecret.trim()) {
      setProblem('Escribe la clave de API y el secreto.')
      return
    }
    setProblem(null)
    connect.mutate(
      { apiKey: apiKey.trim(), apiSecret: apiSecret.trim() },
      {
        onSuccess: () => {
          // The secret is never kept on screen once it is saved.
          setApiKey('')
          setApiSecret('')
          toast.show('Binance conectada')
        },
      },
    )
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-3.5">
      <p className="text-sm leading-5 text-slate-400">
        Pega una clave de API creada en Binance con permiso solo de lectura. Se rechazan las claves que puedan operar
        o retirar.
      </p>
      <TextField
        label="Clave de API"
        autoComplete="off"
        autoCapitalize="none"
        autoCorrect="off"
        value={apiKey}
        onChange={(e) => setApiKey(e.target.value)}
      />
      <TextField
        label="Secreto"
        type="password"
        autoComplete="off"
        autoCapitalize="none"
        value={apiSecret}
        onChange={(e) => setApiSecret(e.target.value)}
      />
      {problem ? (
        <p role="alert" className="text-sm text-red-400">
          {problem}
        </p>
      ) : null}
      <FormError error={connect.error} />
      <Button type="submit" disabled={connect.isPending}>
        {connect.isPending ? 'Conectando…' : 'Conectar'}
      </Button>
      <p className="text-[13px] text-slate-500">El secreto no se vuelve a mostrar después de guardarlo.</p>
    </form>
  )
}

function ConnectedPanel({ integration }: { integration: Integration }) {
  const toast = useToast()
  const sync = useSyncBinance()
  const disconnect = useDisconnectBinance()
  const [confirming, setConfirming] = useState(false)

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm leading-5 text-slate-400">
        {integration.last_synced_at ? `Última lectura: ${formatDateTime(integration.last_synced_at)}. ` : 'Aún no se ha leído. '}
        Solo lectura: la clave se guarda cifrada.
      </p>
      {integration.warnings.map((warning) => (
        <p
          key={warning.code}
          role="status"
          className="rounded-2xl border border-amber-400/35 bg-amber-400/10 p-3 text-[13px] leading-[19px] text-amber-200"
        >
          {warning.message}
        </p>
      ))}
      <FormError error={sync.error ?? disconnect.error} />
      {confirming ? (
        <div role="alertdialog" aria-labelledby="disconnect-title" className="flex flex-col gap-3 rounded-2xl border border-red-900 p-4">
          <p id="disconnect-title" className="font-medium">
            ¿Desconectar Binance? Se borra la clave guardada. Los saldos y operaciones ya leídos se conservan.
          </p>
          <div className="grid grid-cols-2 gap-2">
            <Button variant="secondary" onClick={() => setConfirming(false)}>
              Cancelar
            </Button>
            <Button
              variant="danger"
              disabled={disconnect.isPending}
              onClick={() =>
                disconnect.mutate(undefined, {
                  onSuccess: () => {
                    setConfirming(false)
                    toast.show('Binance desconectada')
                  },
                })
              }
            >
              {disconnect.isPending ? 'Desconectando…' : 'Desconectar'}
            </Button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <Button
            disabled={sync.isPending}
            onClick={() =>
              sync.mutate(undefined, {
                onSuccess: (result) =>
                  toast.show(
                    result.new_trades > 0 ? `Sincronizado: ${result.new_trades} operaciones nuevas` : 'Sincronizado',
                  ),
              })
            }
          >
            {sync.isPending ? 'Sincronizando…' : 'Sincronizar'}
          </Button>
          <Button variant="danger" onClick={() => setConfirming(true)}>
            Desconectar
          </Button>
        </div>
      )}
    </div>
  )
}

export function BinanceScreen() {
  const integrations = useIntegrations()
  const binance = integrations.data?.find((item) => item.provider === 'binance')
  const status = binance?.status ?? 'disconnected'

  return (
    <>
      <PageHeader title="Binance" back={{ to: '/crypto', label: 'Volver a Cripto' }} />
      {integrations.isPending ? (
        <ListSkeleton rows={3} label="Cargando la conexión" />
      ) : integrations.isError ? (
        <ErrorState error={integrations.error} onRetry={() => void integrations.refetch()} />
      ) : (
        <Card>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-[17px] font-semibold">Conexión</h2>
            <StatusChip status={status} />
          </div>
          {binance && status !== 'disconnected' ? <ConnectedPanel integration={binance} /> : null}
          {status === 'error' ? <p className="mt-3 text-sm text-slate-400">Conecta una clave nueva de solo lectura.</p> : null}
          {status !== 'active' ? <ConnectForm /> : null}
        </Card>
      )}
    </>
  )
}
