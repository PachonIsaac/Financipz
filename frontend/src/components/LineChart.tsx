import { shortMonth } from '../features/summary'
import { formatMoney } from '../lib/money'

export interface LinePoint {
  /** YYYY-MM-DD */
  day: string
  /** Decimal string, in dollars */
  value: string
}

const WIDTH = 330
const LEFT = 6
const RIGHT = 324
const TOP = 20
const BASELINE = 100

function label(day: string): string {
  const [year = '', month = '', date = ''] = day.split('-')
  return `${Number(date)} ${shortMonth(`${year}-${month}`).replace('.', '')}`
}

function whole(value: number): string {
  return Math.round(value).toLocaleString('es-CO')
}

/** One series over time: a thin line, a marker on the last day and three quiet guide lines. */
export function LineChart({ points, description }: { points: LinePoint[]; description: string }) {
  const values = points.map((point) => Number(point.value))
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const step = points.length > 1 ? (RIGHT - LEFT) / (points.length - 1) : 0
  const x = (index: number) => (points.length > 1 ? LEFT + index * step : RIGHT)
  const y = (value: number) => (max === min ? (TOP + BASELINE) / 2 : BASELINE - ((value - min) / span) * (BASELINE - TOP))
  const last = points.length - 1
  const middle = Math.floor(last / 2)

  return (
    <figure className="m-0">
      <svg viewBox={`0 0 ${WIDTH} 130`} width="100%" role="img" aria-label={description} className="block">
        <g stroke="#26262a">
          <line x1="0" x2={WIDTH} y1={TOP} y2={TOP} />
          <line x1="0" x2={WIDTH} y1={(TOP + BASELINE) / 2} y2={(TOP + BASELINE) / 2} />
          <line x1="0" x2={WIDTH} y1={BASELINE} y2={BASELINE} stroke="#3a3a40" />
        </g>
        <g fontSize="10" fill="#8a8a92">
          <text x="0" y={TOP - 4}>
            {whole(max)}
          </text>
          <text x="0" y={(TOP + BASELINE) / 2 - 4}>
            {whole((max + min) / 2)}
          </text>
          <text x="0" y={BASELINE - 4}>
            {whole(min)}
          </text>
        </g>
        {points.length > 1 ? (
          <polyline
            fill="none"
            stroke="#e5671a"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            points={values.map((value, index) => `${x(index).toFixed(1)},${y(value).toFixed(1)}`).join(' ')}
          />
        ) : null}
        <circle cx={x(last)} cy={y(values[last] ?? 0)} r="4" fill="#e5671a" stroke="#151517" strokeWidth="2" />
        <g fontSize="11" fill="#8a8a92" textAnchor="middle">
          {points.length > 2 ? <text x={x(middle)} y="122">{label(points[middle]?.day ?? '')}</text> : null}
          {points.length > 1 ? <text x={LEFT + 18} y="122">{label(points[0]?.day ?? '')}</text> : null}
          <text x={RIGHT - 18} y="122" fill="#f5f5f7" fontWeight="600">
            {label(points[last]?.day ?? '')}
          </text>
        </g>
      </svg>
      <table className="sr-only">
        <caption>{description}</caption>
        <thead>
          <tr>
            <th scope="col">Día</th>
            <th scope="col">Valor en dólares</th>
          </tr>
        </thead>
        <tbody>
          {points.map((point) => (
            <tr key={point.day}>
              <th scope="row">{label(point.day)}</th>
              <td>{formatMoney(point.value, 'USD')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  )
}
