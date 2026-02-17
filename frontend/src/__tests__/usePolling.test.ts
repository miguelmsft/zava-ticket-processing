/**
 * Tests for the usePolling hook (hooks/usePolling.ts).
 *
 * Uses real timers with a very short interval for reliable async tests.
 */

import { renderHook, waitFor } from '@testing-library/react'
import { usePolling } from '../hooks/usePolling'

describe('usePolling', () => {
  it('fetches data immediately on mount', async () => {
    const fetchFn = vi.fn().mockResolvedValue({ value: 42 })

    const { result } = renderHook(() => usePolling('key-1', fetchFn, 60_000))

    await waitFor(() => {
      expect(result.current.data).toEqual({ value: 42 })
    })
    expect(fetchFn).toHaveBeenCalled()
    expect(result.current.error).toBeNull()
  })

  it('polls at the given interval', async () => {
    const fetchFn = vi.fn().mockResolvedValue('data')

    renderHook(() => usePolling('key-2', fetchFn, 50)) // 50ms interval

    // After ~150ms we should have multiple calls
    await waitFor(
      () => {
        expect(fetchFn.mock.calls.length).toBeGreaterThanOrEqual(3)
      },
      { timeout: 2000 },
    )
  })

  it('returns null data and clears error when key is null', () => {
    const fetchFn = vi.fn().mockResolvedValue('ignored')

    const { result } = renderHook(() => usePolling(null, fetchFn))

    expect(fetchFn).not.toHaveBeenCalled()
    expect(result.current.data).toBeNull()
    expect(result.current.error).toBeNull()
    expect(result.current.loading).toBe(false)
  })

  it('captures error from failed fetch', async () => {
    const fetchFn = vi.fn().mockRejectedValue(new Error('Network fail'))

    const { result } = renderHook(() => usePolling('key-3', fetchFn, 60_000))

    await waitFor(() => {
      expect(result.current.error).toBe('Network fail')
    })
    expect(result.current.data).toBeNull()
  })

  it('restarts polling when key changes', async () => {
    const fetchFn = vi.fn().mockResolvedValue('v1')

    const { result, rerender } = renderHook(
      ({ key }: { key: string }) => usePolling(key, fetchFn, 60_000),
      { initialProps: { key: 'A' } },
    )

    await waitFor(() => {
      expect(result.current.data).toBe('v1')
    })

    // Change key → should re-invoke
    fetchFn.mockResolvedValue('v2')
    rerender({ key: 'B' })

    await waitFor(() => {
      expect(result.current.data).toBe('v2')
    })
  })

  it('handles non-Error throws gracefully', async () => {
    const fetchFn = vi.fn().mockRejectedValue('string error')

    const { result } = renderHook(() => usePolling('key-4', fetchFn, 60_000))

    await waitFor(() => {
      expect(result.current.error).toBe('Unknown error')
    })
  })

  it('stops polling on unmount', async () => {
    const fetchFn = vi.fn().mockResolvedValue('data')

    const { result, unmount } = renderHook(() =>
      usePolling('key-5', fetchFn, 50),
    )

    await waitFor(() => {
      expect(result.current.data).toBe('data')
    })

    const countAtUnmount = fetchFn.mock.calls.length
    unmount()

    // Wait a bit — count should not increase
    await new Promise((r) => setTimeout(r, 200))
    expect(fetchFn.mock.calls.length).toBe(countAtUnmount)
  })
})
