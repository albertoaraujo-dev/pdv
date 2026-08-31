import type { BillingStatus } from '~/types/billing'

export function useBillingStatus() {
  const config = useRuntimeConfig()
  const apiBase = config.public.apiBase

  return useFetch<BillingStatus>(`${apiBase}/api/billing/status/`, {
    credentials: 'include',
    server: false,
    immediate: true,
    key: 'billing-status'
  })
}
