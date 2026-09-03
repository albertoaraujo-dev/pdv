import type { BillingCatalogPlan } from '~/types/billing'

export function useBillingPlans() {
  const config = useRuntimeConfig()

  return useFetch<BillingCatalogPlan[]>(`${config.public.apiBase}/api/billing/plans/`, {
    server: false,
    immediate: true,
    key: 'billing-catalog-plans'
  })
}
