import type { BillingPlanRequest, BillingPlanRequestPage } from '~/types/billing'

type RequestTarget = { requested_plan?: string; requested_module?: string }

export function useBillingRequests() {
  const config = useRuntimeConfig()
  const url = `${config.public.apiBase}/api/billing/requests/`

  const requests = useFetch<BillingPlanRequestPage>(url, {
    credentials: 'include',
    server: false,
    immediate: true,
    key: 'billing-plan-requests'
  })

  async function createRequest(target: RequestTarget, notes = '', requestKey = crypto.randomUUID()) {
    const csrf = await $fetch<{ csrfToken: string }>(`${config.public.apiBase}/api/auth/csrf/`, {
      credentials: 'include'
    })

    return $fetch<BillingPlanRequest>(url, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'X-CSRFToken': csrf.csrfToken,
        'Idempotency-Key': requestKey
      },
      body: { ...target, request_key: requestKey, notes }
    })
  }

  return { ...requests, createRequest }
}
