// Dates are shown and entered in Colombian time regardless of the device timezone.

const TIME_ZONE = 'America/Bogota'

function parts(date: Date): Record<string, string> {
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  })
  const result: Record<string, string> = {}
  for (const part of formatter.formatToParts(date)) {
    result[part.type] = part.value
  }
  return result
}

/** Today's date as YYYY-MM-DD in Colombian time. */
export function todayLocal(now: Date = new Date()): string {
  const p = parts(now)
  return `${p.year}-${p.month}-${p.day}`
}

/** First day of the month containing `now`, as YYYY-MM-DD. */
export function monthStart(now: Date = new Date()): string {
  return `${todayLocal(now).slice(0, 7)}-01`
}

/**
 * Date-time string sent to the API for a chosen day. Today keeps the current time of day;
 * any other day is set to noon. No offset is sent: the API reads it as Colombian time.
 */
export function toApiDate(day: string, now: Date = new Date()): string {
  if (day === todayLocal(now)) {
    const p = parts(now)
    return `${day}T${p.hour}:${p.minute}:${p.second}`
  }
  return `${day}T12:00:00`
}

/** YYYY-MM-DD of an ISO instant, in Colombian time. */
export function dayOf(iso: string): string {
  return todayLocal(new Date(iso))
}

const dayFormatter = new Intl.DateTimeFormat('es-CO', {
  timeZone: 'UTC',
  weekday: 'long',
  day: 'numeric',
  month: 'long',
})

/** "lunes, 26 de octubre" for a YYYY-MM-DD day. */
export function formatDayHeading(day: string): string {
  return dayFormatter.format(new Date(`${day}T00:00:00Z`))
}

/** "26/10/2026" for a YYYY-MM-DD day. */
export function formatDate(day: string): string {
  const [year, month, date] = day.split('-')
  return `${date}/${month}/${year}`
}

/** "26/10/2026 2:32 p. m." for an ISO instant. */
export function formatDateTime(iso: string): string {
  const time = new Intl.DateTimeFormat('es-CO', {
    timeZone: TIME_ZONE,
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(iso))
  return `${formatDate(dayOf(iso))} ${time}`
}
