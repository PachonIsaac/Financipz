import { Link2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useCryptoHistory, usePortfolio, useTrades } from '../api/hooks'
import type { HistoryPoint, Trade } from '../api/types'
import { Amount } from '../components/Amount'
import { LineChart } from '../components/LineChart'
import { PageHeader } from '../components/Layout'
import { EmptyState, ErrorState, ListSkeleton } from '../components/states'
import { Button, Card } from '../components/ui'
import { TONES } from '../features/appearance'
import { compareDays, signOf, type AssetChange } from '../features/crypto/compare'
import { formatDate, formatDateTime, todayLocal } from '../lib/dates'
import { formatMoney, formatQuantity, formatRate } from '../lib/money'

const HISTORY_DAYS = 30
// Trades shown until the person asks for all of them.
const RECENT_TRADES = 5

function historyStart(): string {
  return todayLocal(new Date(Date.now() - HISTORY_DAYS * 86_400_000))
}

function AssetChip({ asset }: { asset: string }) {
  return (
    <span
      aria-hidden="true"
      className="flex size-10 shrink-0 items-center justify-center rounded-full text-[11px] font-bold"
      style={{ background: `${TONES.orange}29`, color: TONES.orange }}
    >
      {asset.slice(0, 4)}
    </span>
  )
}

/** A change with its sign written out and a color, so it never relies on the color alone. */
function Change({ value, text }: { value: string; text: string }) {
  const direction = signOf(value)
  const sign = direction > 0 ? '+' : direction < 0 ? '−' : ''
  const tone = direction > 0 ? 'text-income' : direction < 0 ? 'text-rose-400' : 'text-slate-400'
  return (
    <span className={`tabular ${tone}`}>
      {sign}
      {text}
    </span>
  )
}

function unsigned(value: string): string {
  return value.startsWith('-') ? value.slice(1) : value
}

function AssetRow({ day, change, compared }: { day: HistoryPoint; change: AssetChange | undefined; compared: boolean }) {
  const held = change ? { asset: change.asset, quantity: change.then } : null
  const item = held ? day.assets.find((entry) => entry.asset === held.asset) : undefined
  return (
    <li className="flex items-start justify-between gap-3 border-t border-slate-800 py-2 first:border-t-0">
      <div className="min-w-0">
        <p className="text-sm">{change?.asset}</p>
        <p className="text-[13px] text-slate-400">
          {item ? `${formatQuantity(item.quantity)} ${item.asset}` : 'No lo tenías ese día'}
        </p>
      </div>
      <div className="text-right text-sm">
        <p className="tabular font-medium">{item?.value_usd ? formatMoney(item.value_usd, 'USD') : item ? 'Sin precio' : '—'}</p>
        {compared && change ? (
          <p className="text-[13px]">
            {change.status === 'gone' ? (
              <span className="text-slate-400">ya no lo tienes</span>
            ) : change.status === 'new' ? (
              <span className="text-slate-400">nuevo desde entonces</span>
            ) : change.status === 'unpriced' ? (
              <span className="text-slate-400">sin precio para comparar</span>
            ) : change.status === 'same' ? (
              <span className="text-slate-400">sin cambio</span>
            ) : (
              <>
                <Change value={change.quantityChange} text={`${formatQuantity(unsigned(change.quantityChange))} ${change.asset}`} />
                {change.valueChange ? (
                  <>
                    {' · '}
                    <Change value={change.valueChange} text={formatMoney(unsigned(change.valueChange), 'USD')} />
                  </>
                ) : null}
              </>
            )}
          </p>
        ) : null}
      </div>
    </li>
  )
}

/** What the portfolio held on the chosen day, and how it changed from then until the last synced day. */
function DayDetail({ day, today }: { day: HistoryPoint; today: HistoryPoint }) {
  const compared = day.date !== today.date
  const comparison = compared ? compareDays(day, today) : null
  const byAsset = new Map(comparison?.assets.map((item) => [item.asset, item]))
  // The assets of that day, then the ones held only now, which that day did not have.
  const rows = comparison
    ? [...day.assets.map((item) => byAsset.get(item.asset)), ...comparison.assets.filter((item) => item.status === 'new')]
    : day.assets.map((item): AssetChange => ({ asset: item.asset, status: 'same', then: item.quantity, now: item.quantity, quantityChange: '0', valueChange: null }))

  return (
    <div aria-live="polite" className="mt-3 rounded-2xl bg-slate-950 p-3">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-sm font-medium">{formatDate(day.date)}</p>
        <p className="tabular text-base font-semibold">{formatMoney(day.total_usd, 'USD')}</p>
      </div>
      {comparison ? (
        <p className="mt-0.5 text-right text-[13px] text-slate-400">
          Hasta hoy: <Change value={comparison.totalChange} text={formatMoney(unsigned(comparison.totalChange), 'USD')} />
          {comparison.percent ? (
            <>
              {' '}
              (<Change value={comparison.totalChange} text={`${unsigned(comparison.percent).replace('.', ',')} %`} />)
            </>
          ) : null}
        </p>
      ) : (
        <p className="mt-0.5 text-right text-[13px] text-slate-400">Último día sincronizado</p>
      )}
      <ul className="mt-2">
        {rows.map((change) =>
          change ? <AssetRow key={change.asset} day={day} change={change} compared={compared} /> : null,
        )}
      </ul>
    </div>
  )
}

function TradeRow({ trade }: { trade: Trade }) {
  const buy = trade.side === 'buy'
  return (
    <li className="flex min-h-[60px] items-center gap-3 border-t border-slate-800 py-2 first:border-t-0">
      <div className="min-w-0 flex-1">
        <p className="text-base">
          {buy ? 'Compra' : 'Venta'} {trade.pair}
        </p>
        <p className="text-[13px] text-slate-400">
          {formatDateTime(trade.executed_at)} · {formatQuantity(trade.quantity)} a {formatQuantity(trade.price)}
        </p>
      </div>
      <p className={`tabular text-base font-semibold ${buy ? 'text-income' : ''}`}>
        {buy ? '+' : '−'}
        {formatQuantity(trade.quantity)}
      </p>
    </li>
  )
}

export function CryptoScreen() {
  const portfolio = usePortfolio()
  const history = useCryptoHistory(historyStart())
  const trades = useTrades()
  const [showAllTrades, setShowAllTrades] = useState(false)
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = trades
  // Asking for all of them loads every page, not only the first.
  useEffect(() => {
    if (showAllTrades && hasNextPage && !isFetchingNextPage) void fetchNextPage()
  }, [showAllTrades, hasNextPage, isFetchingNextPage, fetchNextPage])
  const data = portfolio.data
  const tradeRows = trades.data?.pages.flatMap((page) => page.items) ?? []
  const shownTrades = showAllTrades ? tradeRows : tradeRows.slice(0, RECENT_TRADES)
  const canExpand = hasNextPage || tradeRows.length > RECENT_TRADES
  const days = history.data ?? []
  const points = days.map((point) => ({ day: point.date, value: point.total_usd }))
  // Until a day is touched, the last one is shown.
  const [picked, setPicked] = useState<number | null>(null)
  const selected = Math.min(picked ?? days.length - 1, days.length - 1)

  return (
    <>
      <PageHeader
        title="Cripto"
        back={{ to: '/', label: 'Volver a Inicio' }}
        action={
          <Link
            to="/crypto/binance"
            aria-label="Conexión con Binance"
            className="flex size-11 items-center justify-center rounded-full border border-slate-800 bg-slate-900 text-emerald-500 active:bg-slate-800"
          >
            <Link2 aria-hidden="true" size={20} strokeWidth={1.75} />
          </Link>
        }
      />
      <div className="flex flex-col gap-4">
        {portfolio.isPending ? (
          <ListSkeleton rows={2} label="Cargando el portafolio" />
        ) : portfolio.isError ? (
          <ErrorState error={portfolio.error} onRetry={() => void portfolio.refetch()} />
        ) : !data || data.snapshot_date === null ? (
          <Card>
            <EmptyState
              title="Aún no hay datos de Binance"
              description="Conecta una clave de solo lectura y sincroniza para ver tu portafolio."
              action={
                <Link to="/crypto/binance" className="inline-flex min-h-11 items-center font-medium text-emerald-500">
                  Ir a la conexión
                </Link>
              }
            />
          </Card>
        ) : (
          <>
            <Card className="p-5">
              <h2 className="text-sm font-medium text-slate-400">Portafolio</h2>
              <p className="mt-1 text-[40px] leading-[46px] font-bold tracking-tight" aria-label="Valor del portafolio">
                <Amount value={data.total_usd ?? '0.00'} currency="USD" tone="neutral" />
              </p>
              {data.total_cop ? (
                <p className="text-base text-slate-400">
                  ≈ <Amount value={data.total_cop} currency="COP" tone="neutral" />
                </p>
              ) : null}
              <p className="mt-2.5 text-[13px] text-slate-500">
                Instantánea del {formatDate(data.snapshot_date)}
                {data.rate ? ` · TRM ${formatRate(data.rate.value)}` : ''}
              </p>
            </Card>

            {points.length > 0 ? (
              <Card>
                <div className="flex items-baseline justify-between">
                  <h2 className="text-[17px] font-semibold">Últimos {HISTORY_DAYS} días</h2>
                  <span className="text-[13px] text-slate-400">en dólares</span>
                </div>
                <div className="mt-2.5">
                  <LineChart
                    points={points}
                    description="Valor del portafolio en dólares por día"
                    selected={selected}
                    onSelect={setPicked}
                  />
                </div>
                {days[selected] && days[days.length - 1] ? <DayDetail day={days[selected]} today={days[days.length - 1]!} /> : null}
                <p className="mt-1.5 text-xs text-slate-500">Toca o arrastra sobre la gráfica para ver un día. Los días sin sincronizar no aparecen.</p>
              </Card>
            ) : null}

            <Card className="pb-2">
              <h2 className="mb-1 text-[17px] font-semibold">Activos</h2>
              <ul>
                {data.assets.map((asset) => (
                  <li key={asset.asset} className="flex min-h-16 items-center gap-3 border-t border-slate-800 py-2 first:border-t-0">
                    <AssetChip asset={asset.asset} />
                    <div className="min-w-0 flex-1">
                      <p className="text-base">{asset.asset}</p>
                      <p className="text-[13px] text-slate-400">
                        {formatQuantity(asset.quantity)} {asset.asset}
                      </p>
                    </div>
                    {asset.value_usd ? (
                      <div className="text-right">
                        <p className="tabular text-base font-semibold">{formatMoney(asset.value_usd, 'USD')}</p>
                        {asset.value_cop ? (
                          <p className="tabular text-[13px] text-slate-400">{formatMoney(asset.value_cop, 'COP')}</p>
                        ) : null}
                      </div>
                    ) : (
                      <p className="text-base font-semibold text-slate-400">Sin precio</p>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
            {data.unpriced_assets > 0 ? (
              <p role="status" className="-mt-2 px-1 text-[13px] leading-[19px] text-amber-300">
                {data.unpriced_assets === 1
                  ? '1 activo no tiene precio y no está sumado en el total.'
                  : `${data.unpriced_assets} activos no tienen precio y no están sumados en el total.`}
              </p>
            ) : null}
          </>
        )}

        {trades.isPending ? null : trades.isError ? (
          <ErrorState error={trades.error} onRetry={() => void trades.refetch()} />
        ) : tradeRows.length > 0 ? (
          <Card className="pb-2">
            <h2 className="mb-1 text-[17px] font-semibold">Operaciones recientes</h2>
            <ul>
              {shownTrades.map((trade) => (
                <TradeRow key={trade.id} trade={trade} />
              ))}
            </ul>
            {canExpand ? (
              <Button
                variant="secondary"
                className="my-2 w-full"
                disabled={showAllTrades && isFetchingNextPage}
                onClick={() => setShowAllTrades((value) => !value)}
              >
                {showAllTrades ? (isFetchingNextPage ? 'Cargando…' : 'Ver menos') : 'Ver más'}
              </Button>
            ) : null}
          </Card>
        ) : null}
      </div>
    </>
  )
}

