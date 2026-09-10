<script setup lang="ts">
definePageMeta({ middleware: 'auth' })

type Store = { id: number, name: string, code: string }
type User = { stores: Store[] }
type CashReport = {
  date: string
  sessions_count: number
  sales_count: number
  cancelled_count: number
  completed_total: string
  sales_by_payment: Record<string, string>
  opening_total: string
  supplies_total: string
  withdrawals_total: string
  expected_cash_total: string
  counted_cash_total: string
  variance_total: string
  item_count: string
  average_ticket: string
  top_products: Array<{ product: number, name: string, quantity: string, total: string }>
  by_store: Array<{ store: number, store_name: string, sales_count: number, completed_total: string, expected_cash: string, counted_cash: string, variance: string }>
}

const config = useRuntimeConfig()
const { data: user } = await useFetch<User>(`${config.public.apiBase}/api/auth/me/`, { credentials: 'include', server: false })
const selectedStore = ref<number | null>(user.value?.stores[0]?.id || null)
const reportDate = ref(new Date().toISOString().slice(0, 10))
const report = ref<CashReport | null>(null)
const isLoading = ref(false)
const errorMessage = ref('')

const paymentLabels: Record<string, string> = {
  cash: 'Dinheiro', card_external: 'Cartao externo', pix_manual: 'Pix manual', pix_abacatepay: 'Pix AbacatePay', other: 'Outro'
}

function money(value: string | number) {
  return Number(value || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

async function loadReport() {
  if (!selectedStore.value) return
  isLoading.value = true
  errorMessage.value = ''
  try {
    report.value = await $fetch<CashReport>(`${config.public.apiBase}/api/sales/cash-register/report/?store=${selectedStore.value}&date=${reportDate.value}`, { credentials: 'include' })
  } catch (error: any) {
    errorMessage.value = error?.data?.detail || 'Nao foi possivel carregar o relatorio.'
  } finally {
    isLoading.value = false
  }
}

watch([selectedStore, reportDate], loadReport, { immediate: true })
</script>

<template>
  <main class="reports-shell">
    <header class="reports-header">
      <div>
        <p class="eyebrow">Gestao</p>
        <h1>Fechamento diario</h1>
        <p class="muted">Resumo operacional das vendas e do caixa por loja.</p>
      </div>
      <div class="header-links">
        <NuxtLink to="/pdv">Voltar ao PDV</NuxtLink>
        <a :href="`${config.public.apiBase}/admin/`">Admin Django</a>
      </div>
    </header>

    <section class="filters">
      <label>Loja
        <select v-model.number="selectedStore">
          <option v-for="store in user?.stores || []" :key="store.id" :value="store.id">{{ store.code }} - {{ store.name }}</option>
        </select>
      </label>
      <label>Data
        <input v-model="reportDate" type="date">
      </label>
      <button type="button" :disabled="isLoading" @click="loadReport">{{ isLoading ? 'Carregando...' : 'Atualizar' }}</button>
    </section>

    <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
    <p v-else-if="isLoading" class="muted">Carregando fechamento...</p>
    <template v-else-if="report">
      <section class="metric-grid">
        <article><span>Vendas concluidas</span><strong>{{ money(report.completed_total) }}</strong><small>{{ report.sales_count }} venda(s)</small></article>
        <article><span>Dinheiro esperado</span><strong>{{ money(report.expected_cash_total) }}</strong><small>{{ report.sessions_count }} caixa(s)</small></article>
        <article><span>Dinheiro contado</span><strong>{{ money(report.counted_cash_total) }}</strong><small>apos fechamento</small></article>
        <article :class="{ warning: Number(report.variance_total) !== 0 }"><span>Divergencia</span><strong>{{ money(report.variance_total) }}</strong><small>{{ report.cancelled_count }} cancelada(s)</small></article>
      </section>
      <section class="metric-grid secondary-metrics">
        <article><span>Itens vendidos</span><strong>{{ Number(report.item_count).toLocaleString('pt-BR') }}</strong></article>
        <article><span>Ticket medio</span><strong>{{ money(report.average_ticket) }}</strong></article>
      </section>
      <section class="report-card">
        <h2>Resumo por loja</h2>
        <dl>
          <div v-for="store in report.by_store" :key="store.store"><dt>{{ store.store_name }} <small>{{ store.sales_count }} venda(s)</small></dt><dd>{{ money(store.completed_total) }} · divergência {{ money(store.variance) }}</dd></div>
        </dl>
      </section>
      <section class="report-card">
        <h2>Vendas por forma de pagamento</h2>
        <dl>
          <div v-for="(amount, method) in report.sales_by_payment" :key="method"><dt>{{ paymentLabels[method] || method }}</dt><dd>{{ money(amount) }}</dd></div>
          <div v-if="!Object.keys(report.sales_by_payment).length" class="muted">Nenhuma venda concluida no periodo.</div>
        </dl>
      </section>
      <section class="report-card">
        <h2>Produtos mais vendidos</h2>
        <div v-if="!report.top_products.length" class="muted">Nenhum produto vendido no periodo.</div>
        <dl v-else>
          <div v-for="product in report.top_products" :key="product.product"><dt>{{ product.name }} <small>{{ Number(product.quantity).toLocaleString('pt-BR') }} item(ns)</small></dt><dd>{{ money(product.total) }}</dd></div>
        </dl>
      </section>
    </template>
  </main>
</template>

<style scoped>
.reports-shell { min-height: 100vh; padding: 40px; background: #f8fafc; color: #0f172a; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
.reports-header, .filters, .metric-grid, .report-card { max-width: 1080px; margin: 0 auto; }
.reports-header { display: flex; justify-content: space-between; gap: 24px; align-items: end; }
h1 { margin: 0; font-size: clamp(2rem, 5vw, 3.5rem); letter-spacing: -.05em; }
.eyebrow { margin: 0 0 8px; color: #0369a1; font-size: .75rem; font-weight: 900; letter-spacing: .12em; text-transform: uppercase; }
.muted { color: #64748b; }
.header-links { display: flex; gap: 16px; flex-wrap: wrap; }
a { color: #0369a1; font-weight: 800; }
.filters { display: flex; align-items: end; gap: 14px; margin-top: 32px; padding: 18px; border: 1px solid #dbeafe; border-radius: 18px; background: white; }
label { display: grid; gap: 6px; flex: 1; color: #475569; font-size: .85rem; font-weight: 800; }
input, select { width: 100%; box-sizing: border-box; padding: 11px 12px; border: 1px solid #cbd5e1; border-radius: 10px; background: white; font: inherit; }
button { padding: 11px 16px; border: 0; border-radius: 10px; background: #0369a1; color: white; font: inherit; font-weight: 800; cursor: pointer; }
button:disabled { opacity: .6; cursor: wait; }
.metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-top: 22px; }
article, .report-card { padding: 20px; border: 1px solid #e2e8f0; border-radius: 18px; background: white; }
article { display: grid; gap: 8px; }
article span, article small { color: #64748b; }
article strong { font-size: 1.65rem; }
article.warning { border-color: #fca5a5; background: #fff7f7; }
.report-card { margin-top: 14px; }
.report-card h2 { margin-top: 0; }
dl { display: grid; gap: 12px; }
dl div { display: flex; justify-content: space-between; gap: 16px; padding-bottom: 12px; border-bottom: 1px solid #f1f5f9; }
dt { color: #475569; } dd { margin: 0; font-weight: 900; }
.error { max-width: 1080px; margin: 22px auto; color: #b91c1c; font-weight: 800; }
@media (max-width: 720px) { .reports-shell { padding: 22px; } .reports-header, .filters { display: grid; align-items: stretch; } .metric-grid { grid-template-columns: repeat(2, 1fr); } }
</style>
