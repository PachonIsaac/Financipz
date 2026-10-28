import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useConnectGmail, useDisconnectGmail, useIntegrations, useSyncGmail } from '../api/hooks'
import type { GmailSyncResult } from '../api/types'
import { PageHeader } from '../components/Layout'
import { ErrorState, FormError, ListSkeleton } from '../components/states'
import { useToast } from '../components/Toast'
import { Button, Card } from '../components/ui'
import { formatDateTime } from '../lib/dates'

const RETURN_ERRORS: Record<string, string> = {
  access_denied: 'No se concedió el permiso de lectura del correo.',
  invalid_state: 'La solicitud venció o no es válida. Inténtalo de nuevo.',
  gmail_rejected: 'Google rechazó la solicitud. Inténtalo de nuevo.',
  gmail_not_configured: 'La lectura del correo no está configurada en el servidor.',
}

function SyncSummary({ result }: { result: GmailSyncResult }) {
  if (result.processed === 0) {
    return <p className="text-sm text-slate-400">No hay correos nuevos del banco.</p>
  }
  return (
    <ul className="text-sm text-slate-300">
      <li>Correos leídos: {result.processed}.</li>
      <li>Movimientos nuevos para revisar: {result.created}.</li>
      {result.ignored > 0 ? <li>Avisos que no son movimientos: {result.ignored}.</li> : null}
      {result.unrecognized > 0 ? <li>Correos que no se reconocieron: {result.unrecognized}.</li> : null}
    </ul>
  )
}

export function GmailScreen() {
  const toast = useToast()
  const [params, setParams] = useSearchParams()
  const integrations = useIntegrations()
  const connect = useConnectGmail()
  const sync = useSyncGmail()
  const disconnect = useDisconnectGmail()
  const [confirming, setConfirming] = useState(false)
  // Where the person lands after the consent page: it says whether it worked.
  const returned = params.get('connected') === '1' ? 'connected' : params.get('error')
  const gmail = integrations.data?.find((item) => item.provider === 'gmail')
  const status = gmail?.status ?? 'disconnected'

  function dismissReturn() {
    setParams({}, { replace: true })
  }

  return (
    <>
      <PageHeader title="Correo (Gmail)" back={{ to: '/more', label: 'Volver a Más' }} />
      {returned === 'connected' ? (
        <p role="status" className="mb-4 rounded-2xl bg-income/15 p-3 text-sm text-income">
          Gmail quedó conectado.{' '}
          <button type="button" className="underline" onClick={dismissReturn}>
            Cerrar
          </button>
        </p>
      ) : returned ? (
        <p role="alert" className="mb-4 rounded-2xl bg-red-950 p-3 text-sm text-red-200">
          {RETURN_ERRORS[returned] ?? 'No se pudo conectar Gmail.'}{' '}
          <button type="button" className="underline" onClick={dismissReturn}>
            Cerrar
          </button>
        </p>
      ) : null}

      {integrations.isPending ? (
        <ListSkeleton rows={3} label="Cargando la conexión" />
      ) : integrations.isError ? (
        <ErrorState error={integrations.error} onRetry={() => void integrations.refetch()} />
      ) : (
        <Card>
          <h2 className="text-[17px] font-semibold">Avisos del banco</h2>
          <p className="mt-1 text-sm leading-5 text-slate-400">
            Se lee solo el correo de las alertas del banco, con permiso de solo lectura. Cada aviso llega a Revisión como
            un movimiento pendiente: no cuenta hasta que lo confirmes. No se guarda el texto de los correos.
          </p>

          {status === 'active' && gmail ? (
            <div className="mt-3 flex flex-col gap-3">
              <p className="text-sm text-slate-300">
                {gmail.last_synced_at ? `Última lectura: ${formatDateTime(gmail.last_synced_at)}.` : 'Aún no se ha leído.'}
              </p>
              {sync.data ? <SyncSummary result={sync.data} /> : null}
              <FormError error={sync.error ?? disconnect.error} />
              {confirming ? (
                <div role="alertdialog" aria-labelledby="gmail-disconnect" className="flex flex-col gap-3 rounded-2xl border border-red-900 p-3">
                  <p id="gmail-disconnect" className="text-sm">
                    ¿Desconectar Gmail? Se retira el permiso y se borra el token guardado. Los movimientos ya creados se conservan.
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
                            toast.show('Gmail desconectado')
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
                  <Button disabled={sync.isPending} onClick={() => sync.mutate()}>
                    {sync.isPending ? 'Leyendo…' : 'Leer ahora'}
                  </Button>
                  <Button variant="danger" onClick={() => setConfirming(true)}>
                    Desconectar
                  </Button>
                </div>
              )}
            </div>
          ) : (
            <div className="mt-3 flex flex-col gap-3">
              {status === 'error' && gmail ? (
                <p role="status" className="rounded-2xl border border-amber-400/35 bg-amber-400/10 p-3 text-[13px] leading-[19px] text-amber-200">
                  {gmail.warnings[0]?.message ?? 'La conexión con Gmail dejó de funcionar. Conéctalo de nuevo.'}
                </p>
              ) : null}
              <FormError error={connect.error} />
              <Button
                disabled={connect.isPending}
                onClick={() =>
                  connect.mutate(undefined, { onSuccess: (data) => window.location.assign(data.authorization_url) })
                }
              >
                {connect.isPending ? 'Abriendo…' : 'Conectar Gmail'}
              </Button>
            </div>
          )}
        </Card>
      )}
    </>
  )
}
