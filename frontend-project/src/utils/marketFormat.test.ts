import { describe, expect, it } from 'vitest'
import { formatCompact, formatDateTime, formatPrice, runtimeLabel } from './marketFormat'

describe('marketFormat', () => {
  it('formats prices with stable precision', () => {
    expect(formatPrice(391.6)).toBe('391.60')
    expect(formatPrice(8.2)).toBe('8.20')
    expect(formatPrice(undefined)).toBe('-')
  })

  it('formats large volumes compactly', () => {
    expect(formatCompact(264600)).toBe('264.6K')
    expect(formatCompact(undefined)).toBe('-')
  })

  it('normalizes timestamps and runtime labels', () => {
    expect(formatDateTime('2026-06-09T16:10:00.000+08:00')).toBe('2026-06-09 16:10:00')
    expect(runtimeLabel('LIVE')).toBe('Live')
    expect(runtimeLabel('unknown')).toBe('UNKNOWN')
  })
})
