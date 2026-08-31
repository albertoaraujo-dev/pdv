import type { BillingStatus } from '~/types/billing'

export type ModuleAccessState = 'loading' | 'active' | 'inactive' | 'unavailable'

export function useBillingStatus() {
  const config = useRuntimeConfig()
  const apiBase = config.public.apiBase

  const billing = useFetch<BillingStatus>(`${apiBase}/api/billing/status/`, {
    credentials: 'include',
    server: false,
    immediate: true,
    key: 'billing-status'
  })

  const activeModuleCodes = computed(() => new Set(
    billing.data.value?.effective_modules.map((module) => module.code) || []
  ))

  function hasActiveModule(code: string) {
    return activeModuleCodes.value.has(code)
  }

  function moduleAccessState(code: string): ModuleAccessState {
    if (billing.pending.value) return 'loading'
    if (billing.error.value) return 'unavailable'
    return hasActiveModule(code) ? 'active' : 'inactive'
  }

  return {
    ...billing,
    activeModuleCodes,
    hasActiveModule,
    moduleAccessState
  }
}
