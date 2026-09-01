import type { BillingInvoicePage } from '~/types/billing'

export function useBillingInvoices() {
  const config = useRuntimeConfig()
  const page = ref(1)
  const url = computed(() => `${config.public.apiBase}/api/billing/invoices/?page=${page.value}`)

  const invoices = useFetch<BillingInvoicePage>(url, {
    credentials: 'include',
    server: false,
    immediate: true,
    watch: [page],
    key: 'billing-invoices'
  })

  async function goToPage(nextPage: number) {
    if (nextPage < 1 || nextPage === page.value) return
    page.value = nextPage
  }

  return {
    ...invoices,
    page,
    goToPage
  }
}
