import { Copy } from 'lucide-react'
import { useState } from 'react'
import { useRotateShortcutToken, useShortcutToken } from '../api/hooks'
import { PageHeader } from '../components/Layout'
import { ErrorState, FormError, ListSkeleton } from '../components/states'
import { useToast } from '../components/Toast'
import { Button, Card } from '../components/ui'
import { config } from '../lib/config'
import { formatDateTime } from '../lib/dates'

const STEPS = [
  'En Atajos, crea una automatización personal: «Mensaje», con el remitente de Ualá, y ejecútala sin confirmar.',
  'Agrega la acción «Obtener contenido de URL» con método POST y la URL de arriba.',
  'En Encabezados agrega X-Ingest-Token con el token de arriba.',
  'En el cuerpo, tipo JSON, agrega tres campos: source (texto: sms_uala), text (la variable Mensaje) y received_at (la Fecha actual, en formato ISO 8601).',
]

export function ShortcutScreen() {
  const toast = useToast()
  const status = useShortcutToken()
  const rotate = useRotateShortcutToken()
  const [confirming, setConfirming] = useState(false)
  const created = rotate.data
  const url = `${config.apiUrl.replace(/\/+$/, '')}/ingest/shortcut`

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text)
      toast.show('Copiado')
    } catch {
      toast.show('No se pudo copiar; selecciónalo y cópialo a mano')
    }
  }

  return (
    <>
      <PageHeader title="Atajo de iOS" back={{ to: '/more', label: 'Volver a Más' }} />
      {status.isPending ? (
        <ListSkeleton rows={3} label="Cargando el atajo" />
      ) : status.isError ? (
        <ErrorState error={status.error} onRetry={() => void status.refetch()} />
      ) : (
        <div className="flex flex-col gap-4">
          <Card>
            <h2 className="text-[17px] font-semibold">Token</h2>
            <p className="mt-1 text-sm leading-5 text-slate-400">
              {status.data.configured
                ? `Creado el ${formatDateTime(status.data.created_at ?? '')}. ${
                    status.data.last_used_at ? `Último uso: ${formatDateTime(status.data.last_used_at)}.` : 'Aún no se ha usado.'
                  }`
                : 'Todavía no hay token. Genera uno para que el atajo pueda enviar los mensajes.'}
            </p>
            {created ? (
              <div className="mt-3 flex flex-col gap-2 rounded-2xl border border-emerald-500/40 bg-emerald-500/10 p-3">
                <p className="text-[13px] text-emerald-300">Cópialo ahora: no se vuelve a mostrar.</p>
                <p className="font-mono text-sm break-all" data-testid="token">
                  {created.token}
                </p>
                <Button variant="secondary" onClick={() => void copy(created.token)}>
                  <Copy aria-hidden="true" size={18} className="mr-2" />
                  Copiar token
                </Button>
              </div>
            ) : null}
            <FormError error={rotate.error} />
            {confirming ? (
              <div role="alertdialog" aria-labelledby="rotate-title" className="mt-3 flex flex-col gap-3 rounded-2xl border border-amber-400/40 p-3">
                <p id="rotate-title" className="text-sm">
                  El token actual dejará de funcionar y tendrás que ponerlo de nuevo en el atajo.
                </p>
                <div className="grid grid-cols-2 gap-2">
                  <Button variant="secondary" onClick={() => setConfirming(false)}>
                    Cancelar
                  </Button>
                  <Button
                    disabled={rotate.isPending}
                    onClick={() => rotate.mutate(undefined, { onSuccess: () => setConfirming(false) })}
                  >
                    {rotate.isPending ? 'Generando…' : 'Generar uno nuevo'}
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                className="mt-3 w-full"
                variant={status.data.configured ? 'secondary' : 'primary'}
                disabled={rotate.isPending}
                onClick={() => (status.data.configured ? setConfirming(true) : rotate.mutate())}
              >
                {status.data.configured ? 'Generar un token nuevo' : rotate.isPending ? 'Generando…' : 'Generar token'}
              </Button>
            )}
          </Card>

          <Card>
            <h2 className="text-[17px] font-semibold">Dirección del atajo</h2>
            <p className="mt-1 font-mono text-sm break-all text-slate-300">{url}</p>
            <Button variant="secondary" className="mt-3 w-full" onClick={() => void copy(url)}>
              Copiar dirección
            </Button>
          </Card>

          <Card>
            <h2 className="text-[17px] font-semibold">Cómo armarlo en el iPhone</h2>
            <ol className="mt-2 list-decimal space-y-2 pl-5 text-sm leading-5 text-slate-300">
              {STEPS.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
            <p className="mt-3 text-[13px] text-slate-500">
              Cada mensaje llega a Revisión como un movimiento pendiente: no cuenta hasta que lo confirmes.
            </p>
          </Card>
        </div>
      )}
    </>
  )
}
