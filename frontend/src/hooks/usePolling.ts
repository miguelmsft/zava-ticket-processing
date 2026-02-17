import { useEffect, useState, useRef } from 'react'

/**
 * Generic polling hook.
 *
 * @param key    – When this changes, polling restarts.  Pass `null` to disable.
 * @param fetchFn – The async data-fetching function.  It is stored in a ref so
 *                  a new closure every render does NOT restart the interval.
 * @param intervalMs – Polling interval in milliseconds (default 3 000).
 */
export function usePolling<T>(
  key: string | null,
  fetchFn: () => Promise<T>,
  intervalMs: number = 3000,
) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  // Always keep the latest fetch function in a ref so the effect
  // closure doesn't go stale, yet we don't trigger re-subscriptions.
  const fnRef = useRef(fetchFn)
  fnRef.current = fetchFn

  useEffect(() => {
    if (key === null) {
      setData(null)
      setError(null)
      return
    }

    let active = true

    const poll = async () => {
      if (!active) return
      try {
        setLoading(true)
        const result = await fnRef.current()
        if (active) {
          setData(result)
          setError(null)
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : 'Unknown error')
        }
      } finally {
        if (active) setLoading(false)
      }
    }

    poll()
    const id = setInterval(poll, intervalMs)
    return () => {
      active = false
      clearInterval(id)
    }
  }, [key, intervalMs])

  return { data, error, loading }
}
