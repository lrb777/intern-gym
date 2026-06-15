export function formatPrice(value: unknown) {
  const number = Number(value)
  if (!Number.isFinite(number)) {
    return '-'
  }
  return number.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

export function formatCompact(value: unknown) {
  const number = Number(value)
  if (!Number.isFinite(number)) {
    return '-'
  }
  return Intl.NumberFormat('en-US', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(number)
}

export function formatDateTime(value: unknown) {
  const text = String(value || '')
  if (!text) {
    return '-'
  }
  return text.replace('T', ' ').slice(0, 19)
}

export function runtimeLabel(value: unknown) {
  const text = String(value || '').toUpperCase()
  if (text === 'LIVE') {
    return 'Live'
  }
  if (text === 'WARM') {
    return 'Warm'
  }
  if (text === 'CLOSED') {
    return 'Closed'
  }
  return text || '-'
}
