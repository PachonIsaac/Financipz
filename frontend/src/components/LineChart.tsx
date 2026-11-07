import { useRef, type KeyboardEvent, type PointerEvent } from 'react'
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
const COLOR = '#e5671a'

function label(day: string): string {
  const [year = '', month = '', date = ''] = day.split('-')
  return `${Number(date)} ${shortMonth(`${year}-${month}`).replace('.', '')}`
}

function whole(value: number): string {
  return Math.round(value).toLocaleString('es-CO')
}

/**
 * One series over time: a thin line and three quiet guide lines. A day is chosen by touching or dragging along the
 * chart, or with the arrow keys; the chosen day gets a guide and a marker, and the caller shows what it holds.
 */
export function LineChart({
  points,
  description,
  selected,
  onSelect,
}: {
  points: LinePoint[]
  description: string
  /** Index of the chosen point. */
  selected: number
  onSelect: (index: number) => void
}) {
  const frame = useRef<HTMLDivElement>(null)
  const values = points.map((point) => Number(point.value))
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const step = points.length > 1 ? (RIGHT - LEFT) / (points.length - 1) : 0
  const x = (index: number) => (points.length > 1 ? LEFT + index * step : RIGHT)
  const y = (value: number) => (max === min ? (TOP + BASELINE) / 2 : BASELINE - ((value - min) / span) * (BASELINE - TOP))
  const last = points.length - 1
  const middle = Math.floor(last / 2)
  const chosen = Math.min(Math.max(selected, 0), last)

  function indexAt(clientX: number): number | null {
    const box = frame.current?.getBoundingClientRect()
    if (!box || box.width === 0 || points.length === 0) return null
    const position = ((clientX - box.left) / box.width) * WIDTH
    if (points.length === 1) return 0
    return Math.min(last, Math.max(0, Math.round((position - LEFT) / step)))
  }

  function choose(event: PointerEvent<HTMLDivElement>) {
    const index = indexAt(event.clientX)
    if (index !== null && index !== chosen) onSelect(index)
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const moves: Record<string, number> = { ArrowLeft: chosen - 1, ArrowRight: chosen + 1, Home: 0, End: last }
    const next = moves[event.key]
    if (next === undefined) return
    event.preventDefault()
    onSelect(Math.min(last, Math.max(0, next)))
  }

  return (
    <figure className="m-0">
      <div
        ref={frame}
        role="slider"
        tabIndex={0}
        aria-label={description}
        aria-orientation="horizontal"
        aria-valuemin={0}
        aria-valuemax={last}
        aria-valuenow={chosen}
        aria-valuetext={`${label(points[chosen]?.day ?? '')}: ${formatMoney(points[chosen]?.value ?? '0', 'USD')}`}
        onPointerDown={(event) => {
          // Keeps the drag with this chart even when the finger leaves it.
          event.currentTarget.setPointerCapture?.(event.pointerId)
          choose(event)
        }}
        onPointerMove={(event) => {
          if (event.pointerType === 'mouse' || event.buttons > 0 || event.currentTarget.hasPointerCapture?.(event.pointerId)) {
            choose(event)
          }
        }}
        onKeyDown={onKeyDown}
        // Vertical movement still scrolls the page; horizontal movement chooses the day.
        style={{ touchAction: 'pan-y' }}
        className="rounded-xl outline-offset-2 focus-visible:outline-2 focus-visible:outline-emerald-500"
      >
        <svg viewBox={`0 0 ${WIDTH} 130`} width="100%" aria-hidden="true" className="block select-none">
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
              stroke={COLOR}
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              points={values.map((value, index) => `${x(index).toFixed(1)},${y(value).toFixed(1)}`).join(' ')}
            />
          ) : null}
          <line x1={x(chosen)} x2={x(chosen)} y1={TOP - 8} y2={BASELINE} stroke="#f5f5f7" strokeOpacity="0.35" strokeDasharray="3 3" />
          <circle cx={x(chosen)} cy={y(values[chosen] ?? 0)} r="5" fill={COLOR} stroke="#f5f5f7" strokeWidth="2" />
          <g fontSize="11" fill="#8a8a92" textAnchor="middle">
            {points.length > 2 && chosen !== middle ? <text x={x(middle)} y="122">{label(points[middle]?.day ?? '')}</text> : null}
            {points.length > 1 && chosen !== 0 ? <text x={LEFT + 18} y="122">{label(points[0]?.day ?? '')}</text> : null}
            {points.length > 1 && chosen !== last ? <text x={RIGHT - 18} y="122">{label(points[last]?.day ?? '')}</text> : null}
            <text x={Math.min(RIGHT - 18, Math.max(LEFT + 18, x(chosen)))} y="122" fill="#f5f5f7" fontWeight="600">
              {label(points[chosen]?.day ?? '')}
            </text>
          </g>
        </svg>
      </div>
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
