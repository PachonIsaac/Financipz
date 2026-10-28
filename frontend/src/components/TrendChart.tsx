import type { MonthTotals } from '../api/types'
import { shortMonth } from '../features/summary'
import { formatMoney, toCents } from '../lib/money'

const WIDTH = 318
const PLOT_TOP = 18
const BASELINE = 120
const BAR = 16
const GAP = 2
const RADIUS = 4

// Two series from a palette checked for color-blind separation against the card surface.
const INCOME = '#3f87db'
const EXPENSES = '#e5671a'

/** A column that is rounded only at its top end and sits on the baseline. */
function column(x: number, height: number): string {
  if (height <= 0) return ''
  const r = Math.min(RADIUS, height)
  const top = BASELINE - height
  return `M${x} ${BASELINE}V${top + r}a${r} ${r} 0 0 1 ${r}-${r}h${BAR - 2 * r}a${r} ${r} 0 0 1 ${r} ${r}V${BASELINE}Z`
}

function millions(cents: number): string {
  return (cents / 100_000_000).toLocaleString('es-CO', { maximumFractionDigits: 1 })
}

/** Income and expenses side by side for each month. The last month is the one being looked at. */
export function TrendChart({ data }: { data: MonthTotals[] }) {
  const values = data.map((point) => ({
    month: point.month,
    income: Number(toCents(point.income)),
    expenses: Number(toCents(point.expenses)),
  }))
  const max = Math.max(1, ...values.flatMap((v) => [v.income, v.expenses]))
  const scale = (BASELINE - PLOT_TOP) / max
  const slot = WIDTH / Math.max(1, values.length)
  const first = (slot - (2 * BAR + GAP)) / 2

  return (
    <figure className="m-0">
      <svg viewBox={`0 0 ${WIDTH} 148`} width="100%" role="img" aria-label="Ingresos y gastos de los últimos meses" className="block">
        <g stroke="#26262a">
          {[1, 2, 3].map((step) => {
            const y = BASELINE - ((BASELINE - PLOT_TOP) * step) / 3
            return <line key={step} x1="0" x2={WIDTH} y1={y} y2={y} />
          })}
          <line x1="0" x2={WIDTH} y1={BASELINE} y2={BASELINE} stroke="#3a3a40" />
        </g>
        {values.map((v, index) => {
          const x = index * slot + first
          const last = index === values.length - 1
          return (
            <g key={v.month}>
              <path d={column(x, v.income * scale)} fill={INCOME} />
              <path d={column(x + BAR + GAP, v.expenses * scale)} fill={EXPENSES} />
              {last ? (
                <g fill="#f5f5f7" fontSize="10" fontWeight="600" textAnchor="middle">
                  <text x={x + BAR / 2} y={BASELINE - v.income * scale - 5}>
                    {millions(v.income)}
                  </text>
                  <text x={x + BAR + GAP + BAR / 2} y={BASELINE - v.expenses * scale - 5}>
                    {millions(v.expenses)}
                  </text>
                </g>
              ) : null}
              <text
                x={x + BAR + GAP / 2}
                y="140"
                textAnchor="middle"
                fontSize="11"
                fill={last ? '#f5f5f7' : '#8a8a92'}
                fontWeight={last ? 600 : 400}
              >
                {shortMonth(v.month).replace('.', '')}
              </text>
            </g>
          )
        })}
      </svg>
      <figcaption className="mt-2 flex gap-4 text-xs text-slate-400">
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-[3px]" style={{ background: INCOME }} />
          Ingresos
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-[3px]" style={{ background: EXPENSES }} />
          Gastos
        </span>
      </figcaption>
      <table className="sr-only">
        <caption>Ingresos y gastos por mes</caption>
        <thead>
          <tr>
            <th scope="col">Mes</th>
            <th scope="col">Ingresos</th>
            <th scope="col">Gastos</th>
          </tr>
        </thead>
        <tbody>
          {data.map((point) => (
            <tr key={point.month}>
              <th scope="row">{shortMonth(point.month)}</th>
              <td>{formatMoney(point.income, 'COP')}</td>
              <td>{formatMoney(point.expenses, 'COP')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  )
}
