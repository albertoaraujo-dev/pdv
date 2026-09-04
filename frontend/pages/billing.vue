<script setup lang="ts">
import type { BillingStatus } from '~/types/billing'

definePageMeta({ middleware: 'auth' })

const config = useRuntimeConfig()
const {
  data: status,
  pending: statusPending,
  error: statusError,
  refresh: refreshStatus
} = useFetch<BillingStatus>(`${config.public.apiBase}/api/billing/status/`, {
  credentials: 'include',
  server: false,
  immediate: true,
  key: 'billing-page-status'
})
const {
  data: invoicePage,
  pending: invoicesPending,
  error: invoicesError,
  refresh: refreshInvoices,
  page,
  totalPages,
  goToPage
} = useBillingInvoices()
const {
  data: requestPage,
  pending: requestsPending,
  error: requestsError,
  refresh: refreshRequests
} = useBillingRequests()

const statusLabels: Record<string, string> = {
  trial: 'Em período de teste',
  active: 'Ativa',
  past_due: 'Pagamento pendente',
  suspended: 'Suspensa',
  cancelled: 'Cancelada'
}
const invoiceStatusLabels: Record<string, string> = {
  open: 'Aberta',
  past_due: 'Inadimplente',
  paid: 'Paga',
  void: 'Cancelada'
}
const notificationLabels: Record<string, string> = {
  due_soon: 'Vencimento próximo',
  past_due: 'Fatura vencida',
  suspension_warning: 'Aviso de suspensão',
  suspended: 'Assinatura suspensa'
}
const requestStatusLabels: Record<string, string> = {
  open: 'Em análise',
  approved: 'Aprovada',
  rejected: 'Rejeitada',
  cancelled: 'Cancelada'
}

const statusForbidden = computed(() => statusError.value?.statusCode === 403)
const invoicesForbidden = computed(() => invoicesError.value?.statusCode === 403)
const statusHasError = computed(() => Boolean(statusError.value) && !statusForbidden.value)
const invoicesHaveError = computed(() => Boolean(invoicesError.value) && !invoicesForbidden.value)
const warningNotifications = computed(() => status.value?.recent_notifications || [])

function label(labels: Record<string, string>, value: string) {
  return labels[value] || value
}

function formatDate(value: string | null) {
  if (!value) return 'Não informado'
  const date = /^\d{4}-\d{2}-\d{2}$/.test(value)
    ? new Date(`${value}T00:00:00`)
    : new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('pt-BR')
}

function formatPeriod(start: string | null, end: string | null) {
  if (!start || !end) return 'Não informado'
  return `${formatDate(start)} a ${formatDate(end)}`
}

function formatAmount(value: string) {
  const amount = Number(value)
  return Number.isNaN(amount) ? value : amount.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

function retryStatus() {
  return refreshStatus()
}

function retryInvoices() {
  return refreshInvoices()
}

function retryRequests() {
  return refreshRequests()
}

function requestTarget(request: { requested_plan: string | null; requested_module: string | null }) {
  if (request.requested_plan) return `Plano: ${request.requested_plan}`
  if (request.requested_module) return `Add-on PLUS: ${request.requested_module}`
  return 'Destino não informado'
}
</script>

<template>
  <main class="billing-shell">
    <header class="billing-header">
      <div>
        <p class="eyebrow">Conta e cobrança</p>
        <h1>Billing</h1>
        <p class="subtitle">Consulte a assinatura e o histórico de faturas da sua organização.</p>
      </div>
      <NuxtLink class="back-link" to="/pdv">Voltar ao PDV</NuxtLink>
    </header>

    <section class="panel" aria-labelledby="subscription-title">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">Assinatura</p>
          <h2 id="subscription-title">Status do plano</h2>
        </div>
        <button v-if="statusHasError" type="button" class="secondary-button" :disabled="statusPending" @click="retryStatus">
          Tentar novamente
        </button>
      </div>

      <p v-if="statusPending" class="muted">Carregando status da assinatura...</p>
      <div v-else-if="statusForbidden" class="message warning">Seu usuário não tem permissão para consultar o billing.</div>
      <div v-else-if="statusHasError" class="message error">Não foi possível carregar o status da assinatura.</div>
      <p v-else-if="!status?.subscription" class="muted">Nenhuma assinatura foi configurada para esta organização.</p>
      <div v-else class="summary-grid">
        <div><span>Plano</span><strong>{{ status.subscription.plan.name }}</strong></div>
        <div><span>Status</span><strong class="status-pill" :class="`status-${status.subscription.status}`">{{ label(statusLabels, status.subscription.status) }}</strong></div>
        <div><span>Período atual</span><strong>{{ formatPeriod(status.subscription.current_period_start, status.subscription.current_period_end) }}</strong></div>
      </div>

      <div v-if="warningNotifications.length" class="warnings">
        <h3>Avisos recentes</h3>
        <ul>
          <li v-for="notification in warningNotifications" :key="`${notification.type}-${notification.created_at}`">
            <strong>{{ label(notificationLabels, notification.type) }}</strong>
            <span>{{ formatDate(notification.created_at) }}</span>
          </li>
        </ul>
      </div>
    </section>

    <section class="panel" aria-labelledby="requests-title">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">Acompanhamento</p>
          <h2 id="requests-title">Solicitações de plano e PLUS</h2>
        </div>
        <button v-if="requestsError" type="button" class="secondary-button" :disabled="requestsPending" @click="retryRequests">Tentar novamente</button>
      </div>

      <p v-if="requestsPending" class="muted">Carregando solicitações...</p>
      <div v-else-if="requestsError?.statusCode === 403" class="message warning">Seu perfil não pode consultar solicitações de billing.</div>
      <div v-else-if="requestsError" class="message error">Não foi possível carregar as solicitações agora.</div>
      <p v-else-if="!requestPage?.results.length" class="empty-state">Nenhuma solicitação encontrada. Para solicitar um plano ou add-on, fale com a equipe responsável.</p>
      <div v-else class="request-list">
        <article v-for="request in requestPage.results" :key="request.id" class="request-row">
          <div>
            <strong>{{ requestTarget(request) }}</strong>
            <span>Solicitada por {{ request.requester }} em {{ formatDate(request.created_at) }}</span>
            <span v-if="request.notes">{{ request.notes }}</span>
          </div>
          <span class="status-pill" :class="`status-${request.status}`">{{ label(requestStatusLabels, request.status) }}</span>
        </article>
      </div>
    </section>

    <section class="panel" aria-labelledby="invoices-title">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">Histórico</p>
          <h2 id="invoices-title">Faturas</h2>
        </div>
        <button v-if="invoicesHaveError" type="button" class="secondary-button" :disabled="invoicesPending" @click="retryInvoices">
          Tentar novamente
        </button>
      </div>

      <p v-if="invoicesPending" class="muted">Carregando faturas...</p>
      <div v-else-if="invoicesForbidden" class="message warning">Seu usuário não tem permissão para consultar as faturas.</div>
      <div v-else-if="invoicesHaveError" class="message error">Não foi possível carregar o histórico de faturas.</div>
      <p v-else-if="!invoicePage?.results.length" class="empty-state">Nenhuma fatura encontrada.</p>
      <template v-else>
        <div class="table-wrap">
          <table>
            <thead>
              <tr><th>Fatura</th><th>Plano</th><th>Valor</th><th>Status</th><th>Vencimento</th><th>Período</th><th>Pago em</th></tr>
            </thead>
            <tbody>
              <tr v-for="invoice in invoicePage.results" :key="invoice.public_id">
                <th scope="row">{{ invoice.number }}</th>
                <td>{{ invoice.plan.name }}</td>
                <td>{{ formatAmount(invoice.amount) }}</td>
                <td><span class="status-pill" :class="`status-${invoice.status}`">{{ label(invoiceStatusLabels, invoice.status) }}</span></td>
                <td>{{ formatDate(invoice.due_date) }}</td>
                <td>{{ formatPeriod(invoice.period_start, invoice.period_end) }}</td>
                <td>{{ formatDate(invoice.paid_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <nav v-if="invoicePage?.next || invoicePage?.previous" class="pagination" aria-label="Paginação de faturas">
          <button type="button" :disabled="!invoicePage.previous || invoicesPending" @click="goToPage(page - 1)">Anterior</button>
          <span>Página {{ page }}</span>
          <button type="button" :disabled="!invoicePage.next || invoicesPending" @click="goToPage(page + 1)">Próxima</button>
        </nav>
      </template>
    </section>
  </main>
</template>

<style scoped>
.billing-shell { min-height: 100vh; padding: 40px clamp(20px, 5vw, 64px); background: #f8fafc; color: #0f172a; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
.billing-header, .panel-heading, .pagination { display: flex; justify-content: space-between; gap: 24px; }
.billing-header { align-items: flex-start; max-width: 1200px; margin: 0 auto 28px; }
.eyebrow { margin: 0 0 6px; color: #0369a1; font-size: .76rem; font-weight: 900; letter-spacing: .14em; text-transform: uppercase; }
h1, h2, h3 { margin: 0; } h1 { font-size: clamp(2.2rem, 5vw, 4rem); letter-spacing: -.05em; } h2 { font-size: 1.4rem; } h3 { margin-bottom: 10px; font-size: .9rem; }
.subtitle, .muted { color: #64748b; } .subtitle { margin: 10px 0 0; }
.back-link, .secondary-button, .pagination button { border: 0; border-radius: 10px; padding: 10px 14px; font-weight: 800; text-decoration: none; cursor: pointer; }
.back-link { background: #0f172a; color: #fff; } .secondary-button, .pagination button { background: #e2e8f0; color: #0f172a; }
button:disabled { cursor: wait; opacity: .55; }
.panel { max-width: 1200px; margin: 0 auto 24px; padding: clamp(20px, 4vw, 30px); border: 1px solid #dbeafe; border-radius: 20px; background: #fff; box-shadow: 0 12px 32px rgba(15,23,42,.06); }
.panel-heading { align-items: flex-start; margin-bottom: 22px; } .summary-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; padding: 18px 0; border-top: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0; }
.summary-grid div { display: grid; gap: 6px; } .summary-grid span, td, th:not([scope="row"]) { color: #64748b; font-size: .84rem; } .summary-grid strong { font-size: 1.05rem; }
.status-pill { display: inline-block; width: fit-content; padding: 4px 8px; border-radius: 999px; background: #dcfce7; color: #166534; font-size: .8rem; font-weight: 800; } .status-past_due, .status-suspended, .status-cancelled, .status-void { background: #fef3c7; color: #92400e; } .status-rejected { background: #fee2e2; color: #991b1b; } .status-paid { background: #dcfce7; color: #166534; }
.warnings { margin-top: 20px; } .warnings ul { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; } .warnings li { display: flex; justify-content: space-between; gap: 14px; padding: 10px 12px; border-radius: 10px; background: #fffbeb; color: #92400e; } .warnings span { color: #a16207; }
.message, .empty-state { margin: 0; padding: 13px; border-radius: 10px; } .message.error { background: #fef2f2; color: #991b1b; } .message.warning, .empty-state { background: #f8fafc; color: #475569; }
.request-list { display: grid; gap: 10px; } .request-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 18px; padding: 14px; border: 1px solid #e2e8f0; border-radius: 12px; } .request-row div { display: grid; gap: 5px; } .request-row span:not(.status-pill) { color: #64748b; font-size: .84rem; }
.table-wrap { overflow-x: auto; } table { width: 100%; min-width: 850px; border-collapse: collapse; } th, td { padding: 14px 12px; border-bottom: 1px solid #e2e8f0; text-align: left; white-space: nowrap; } th[scope="row"] { font-weight: 800; }
.pagination { align-items: center; justify-content: flex-end; margin-top: 18px; color: #475569; font-size: .9rem; } .pagination button { border: 1px solid #cbd5e1; background: #fff; }
@media (max-width: 680px) { .billing-header, .panel-heading { flex-direction: column; } .summary-grid { grid-template-columns: 1fr; } .billing-header .back-link { align-self: flex-start; } .pagination { justify-content: space-between; flex-wrap: wrap; } .request-row { flex-direction: column; } }
</style>
