import { useCallback, useEffect, useRef, useState } from 'react'
import { warmUp } from '../lib/warmup'

export type WarmupState = { status: 'checking'; seconds: number } | { status: 'ready' } | { status: 'failed' }

const RECHECK_AFTER_MS = 10 * 60_000

/** Wakes the server as soon as the app opens, and again when the app returns after a long pause. */
export function useWarmup(apiUrl: string): { state: WarmupState; retry: () => void } {
  const [state, setState] = useState<WarmupState>(apiUrl ? { status: 'checking', seconds: 0 } : { status: 'ready' })
  const [attempt, setAttempt] = useState(0)
  const lastSuccess = useRef(0)

  useEffect(() => {
    if (!apiUrl) return
    const controller = new AbortController()
    const started = Date.now()
    const ticker = setInterval(
      () => setState((current) => (current.status === 'checking' ? { status: 'checking', seconds: Math.round((Date.now() - started) / 1000) } : current)),
      1000,
    )
    void warmUp({ healthUrl: `${apiUrl.replace(/\/+$/, '')}/health`, signal: controller.signal }).then((awake) => {
      if (controller.signal.aborted) return
      if (awake) lastSuccess.current = Date.now()
      setState(awake ? { status: 'ready' } : { status: 'failed' })
    })
    return () => {
      controller.abort()
      clearInterval(ticker)
    }
  }, [apiUrl, attempt])

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible' && lastSuccess.current && Date.now() - lastSuccess.current > RECHECK_AFTER_MS) {
        lastSuccess.current = 0
        setState({ status: 'checking', seconds: 0 })
        setAttempt((n) => n + 1)
      }
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [])

  const retry = useCallback(() => {
    setState({ status: 'checking', seconds: 0 })
    setAttempt((n) => n + 1)
  }, [])
  return { state, retry }
}
