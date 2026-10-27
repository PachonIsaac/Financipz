import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { stubLocalStorage } from '../test/utils'
import { writeStored } from './storage'
import { readWakeUps, warmUp } from './warmup'

const URL = 'http://api.test/api/v1/health'

beforeEach(() => {
  stubLocalStorage()
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('warmUp', () => {
  it('resolves at once when the server is already awake, and records nothing', async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response('{}', { status: 200 }))

    await expect(warmUp({ healthUrl: URL, fetchImpl })).resolves.toBe(true)

    expect(fetchImpl).toHaveBeenCalledTimes(1)
    expect(fetchImpl.mock.calls[0]![1]).toMatchObject({ cache: 'no-store' })
    expect(readWakeUps()).toEqual([])
  })

  it('keeps trying through gateway errors and network failures, and records how long the wake took', async () => {
    const answers = [new Response('', { status: 503 }), new Error('network'), new Response('{}', { status: 200 })]
    const fetchImpl = vi.fn<typeof fetch>(async () => {
      const next = answers.shift()!
      if (next instanceof Error) throw next
      if (answers.length === 0) await new Promise((resolve) => setTimeout(resolve, 20_000))
      return next
    })

    const result = warmUp({ healthUrl: URL, fetchImpl, intervalMs: 3_000 })
    await vi.advanceTimersByTimeAsync(40_000)

    await expect(result).resolves.toBe(true)
    expect(fetchImpl).toHaveBeenCalledTimes(3)
    expect(readWakeUps()).toHaveLength(1)
    expect(readWakeUps()[0]!.seconds).toBeGreaterThanOrEqual(5)
  })

  it('gives up after the total time', async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => {
      throw new Error('network')
    })

    const result = warmUp({ healthUrl: URL, fetchImpl, intervalMs: 3_000, totalMs: 10_000 })
    await vi.advanceTimersByTimeAsync(20_000)

    await expect(result).resolves.toBe(false)
    expect(readWakeUps()).toEqual([])
  })

  it('stops when it is aborted', async () => {
    const controller = new AbortController()
    const fetchImpl = vi.fn<typeof fetch>(async () => {
      throw new Error('network')
    })

    const result = warmUp({ healthUrl: URL, fetchImpl, signal: controller.signal })
    await vi.advanceTimersByTimeAsync(100)
    controller.abort()
    await vi.advanceTimersByTimeAsync(5_000)

    await expect(result).resolves.toBe(false)
    expect(fetchImpl.mock.calls.length).toBeLessThanOrEqual(2)
  })

  it('keeps only the last ten wake-ups and ignores a damaged record', async () => {
    writeStored('financipz.wakeups', 'not json')
    expect(readWakeUps()).toEqual([])

    for (let index = 0; index < 12; index += 1) {
      const fetchImpl = vi.fn<typeof fetch>(async () => {
        await new Promise((resolve) => setTimeout(resolve, 6_000))
        return new Response('{}')
      })
      const result = warmUp({ healthUrl: URL, fetchImpl })
      await vi.advanceTimersByTimeAsync(7_000)
      await result
    }

    expect(readWakeUps()).toHaveLength(10)
  })
})
