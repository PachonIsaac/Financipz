// A free server sleeps when idle and takes about a minute to wake. Asking for its health as soon as the
// app opens wakes it while the person is still signing in, and the time it takes is kept to review it.
import { readStored, writeStored } from './storage'

const STORAGE_KEY = 'financipz.wakeups'
const KEPT = 10
// Faster answers come from a server that was already awake, so they are not wake-ups.
const WAKE_THRESHOLD_MS = 5_000

export interface WakeUp {
  at: string
  seconds: number
}

export function readWakeUps(): WakeUp[] {
  try {
    const parsed: unknown = JSON.parse(readStored(STORAGE_KEY) ?? '[]')
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (item): item is WakeUp =>
        !!item && typeof item === 'object' && typeof item.at === 'string' && typeof item.seconds === 'number',
    )
  } catch {
    return []
  }
}

function recordWakeUp(elapsedMs: number): void {
  if (elapsedMs < WAKE_THRESHOLD_MS) return
  const entry = { at: new Date().toISOString(), seconds: Math.round(elapsedMs / 1000) }
  writeStored(STORAGE_KEY, JSON.stringify([...readWakeUps(), entry].slice(-KEPT)))
}

export interface WarmUpOptions {
  healthUrl: string
  signal?: AbortSignal
  fetchImpl?: typeof fetch
  /** Longest wait for each attempt. */
  attemptMs?: number
  /** Pause between attempts. */
  intervalMs?: number
  /** Give up after this long in total. */
  totalMs?: number
}

/** Asks for the server's health until it answers. Resolves true once it is awake, false if it gives up. */
export async function warmUp(options: WarmUpOptions): Promise<boolean> {
  const { healthUrl, signal, attemptMs = 20_000, intervalMs = 3_000, totalMs = 120_000 } = options
  const doFetch = options.fetchImpl ?? ((...args: Parameters<typeof fetch>) => fetch(...args))
  const started = Date.now()

  while (!signal?.aborted && Date.now() - started < totalMs) {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), attemptMs)
    const stop = () => controller.abort()
    signal?.addEventListener('abort', stop)
    try {
      const response = await doFetch(healthUrl, { cache: 'no-store', signal: controller.signal })
      // While it wakes, the host answers with a gateway error (5xx) or none that the browser can read.
      if (response.status < 500) {
        recordWakeUp(Date.now() - started)
        return true
      }
    } catch {
      // Not awake yet, or no connection: try again.
    } finally {
      clearTimeout(timer)
      signal?.removeEventListener('abort', stop)
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }
  return false
}
