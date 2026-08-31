<script setup lang="ts">
import type { BillingModule, BillingNotification } from '~/types/billing'

const { data, error, pending, refresh } = useBillingStatus()

const statusLabels: Record<string, string> = {
  trial: 'Em período de teste',
  active: 'Ativa',
  past_due: 'Pagamento pendente',
  suspended: 'Suspensa',
  cancelled: 'Cancelada'
}

const notificationLabels: Record<string, string> = {
  due_soon: 'Vencimento próximo',
  past_due: 'Fatura vencida',
  suspension_warning: 'Aviso de suspensão',
  suspended: 'Assinatura suspensa'
}

const isForbidden = computed(() => error.value?.statusCode === 403)
const hasRequestError = computed(() => Boolean(error.value) && !isForbidden.value)

function statusLabel(status: string) {
  return statusLabels[status] || status
}

function notificationLabel(notification: BillingNotification) {
  return notificationLabels[notification.type] || notification.type
}

function formatDate(value: string | null) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('pt-BR')
}

function formatLimitKey(key: string) {
  return key.replaceAll('_', ' ')
}

function moduleLimits(module: BillingModule) {
  return Object.entries(module.limits || {})
    .map(([key, value]) => `${formatLimitKey(key)}: ${String(value)}`)
    .join(' · ')
}
</script>

<template>
  <section class="billing-card" aria-labelledby="billing-status-title">
    <div class="billing-heading">
      <div>
        <p class="eyebrow">Assinatura</p>
        <h2 id="billing-status-title">Status do plano</h2>
      </div>
      <button v-if="hasRequestError" type="button" class="refresh-button" :disabled="pending" @click="refresh">
        Tentar novamente
      </button>
    </div>

    <p v-if="pending" class="billing-muted">Carregando informações de billing...</p>
    <p v-else-if="isForbidden" class="billing-muted">As informações de billing não estão disponíveis para este usuário.</p>
    <p v-else-if="hasRequestError" class="billing-message billing-message-error">Não foi possível carregar o status do plano agora.</p>
    <template v-else-if="!data?.subscription">
      <p class="billing-muted">Nenhuma assinatura foi configurada para esta organização.</p>
    </template>
    <template v-else>
      <div class="billing-summary">
        <div>
          <span>Plano</span>
          <strong>{{ data.subscription.plan.name }}</strong>
        </div>
        <div>
          <span>Status</span>
          <strong :class="`billing-status billing-status-${data.subscription.status}`">{{ statusLabel(data.subscription.status) }}</strong>
        </div>
        <div v-if="data.subscription.current_period_end">
          <span>Período até</span>
          <strong>{{ formatDate(data.subscription.current_period_end) }}</strong>
        </div>
      </div>

      <div class="billing-section">
        <h3>Módulos ativos</h3>
        <p v-if="!data.effective_modules.length" class="billing-muted">Nenhum módulo ativo no momento.</p>
        <ul v-else class="module-list">
          <li v-for="module in data.effective_modules" :key="module.code">
            <strong>{{ module.name }}</strong>
            <small v-if="moduleLimits(module)">{{ moduleLimits(module) }}</small>
          </li>
        </ul>
      </div>

    </template>

    <div v-if="data?.recent_notifications.length" class="billing-section">
      <h3>Avisos recentes</h3>
      <ul class="notification-list">
        <li v-for="notification in data.recent_notifications" :key="`${notification.type}-${notification.created_at}`">
          <strong>{{ notificationLabel(notification) }}</strong>
          <small>{{ formatDate(notification.created_at) }}</small>
        </li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.billing-card {
  max-width: 820px;
  margin-bottom: 24px;
  padding: 24px;
  border: 1px solid #dbeafe;
  border-radius: 20px;
  background: #f8fbff;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.06);
}

.billing-heading,
.billing-summary,
.module-list li,
.notification-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.billing-heading {
  align-items: flex-start;
  margin-bottom: 18px;
}

.eyebrow {
  margin: 0 0 6px;
  color: #0369a1;
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

h2,
h3 {
  margin: 0;
}

h2 {
  font-size: 1.45rem;
}

h3 {
  margin-bottom: 10px;
  font-size: 0.9rem;
  color: #475569;
}

.billing-summary {
  align-items: flex-start;
  justify-content: flex-start;
  flex-wrap: wrap;
  padding: 14px 0;
  border-top: 1px solid #dbeafe;
  border-bottom: 1px solid #dbeafe;
}

.billing-summary div {
  display: grid;
  gap: 4px;
  min-width: 130px;
}

.billing-summary span,
.billing-muted,
small {
  color: #64748b;
}

.billing-summary span,
small {
  font-size: 0.82rem;
}

.billing-status-past_due,
.billing-status-suspended,
.billing-status-cancelled {
  color: #b45309;
}

.billing-section {
  margin-top: 18px;
}

.module-list,
.notification-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.module-list li,
.notification-list li {
  align-items: flex-start;
  padding: 10px 12px;
  border-radius: 10px;
  background: #ffffff;
}

.module-list small {
  text-align: right;
}

.notification-list li {
  border: 1px solid #fde68a;
  background: #fffbeb;
  color: #92400e;
}

.notification-list small {
  color: #a16207;
  white-space: nowrap;
}

.billing-muted {
  margin: 0;
}

.billing-message {
  margin: 0;
  padding: 10px 12px;
  border-radius: 10px;
}

.billing-message-error {
  border: 1px solid #fecaca;
  background: #fef2f2;
  color: #991b1b;
}

.refresh-button {
  margin: 0;
  padding: 8px 10px;
  border: 0;
  border-radius: 9px;
  background: #0f172a;
  color: #ffffff;
  font-weight: 800;
  cursor: pointer;
}

.refresh-button:disabled {
  cursor: wait;
  opacity: 0.65;
}

@media (max-width: 560px) {
  .billing-card {
    padding: 18px;
  }

  .module-list li,
  .notification-list li {
    display: grid;
    gap: 4px;
  }

  .module-list small,
  .notification-list small {
    text-align: left;
    white-space: normal;
  }
}
</style>
