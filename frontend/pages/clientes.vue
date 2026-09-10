<script setup lang="ts">
definePageMeta({ middleware: 'auth' })

type Customer = { id: number, name: string, phone: string, email: string, document: string, sales_count: number }
type Sale = { id: number, total_amount: string, status: string, payment_method_label: string, created_at: string }
type History = { customer: Customer, sales_count: number, completed_sales_count: number, completed_total: string, last_sale_at: string | null, sales: Sale[] }
const config = useRuntimeConfig()
const search = ref('')
const selectedId = ref<number | null>(null)
const isEditing = ref(false)
const editName = ref('')
const editPhone = ref('')
const editEmail = ref('')
const isSaving = ref(false)
const listUrl = computed(() => `${config.public.apiBase}/api/sales/customers/${search.value ? `?q=${encodeURIComponent(search.value)}` : ''}`)
const { data: customers, pending: loadingCustomers, refresh: refreshCustomers } = await useFetch<{ results: Customer[] }>(listUrl, { credentials: 'include', server: false, watch: false })
const { data: history, pending: loadingHistory, refresh: refreshHistory } = await useFetch<History>(() => `${config.public.apiBase}/api/sales/customers/${selectedId.value}/history/`, { credentials: 'include', server: false, immediate: false, watch: false })

function money(value: string) { return Number(value || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }) }
async function selectCustomer(id: number) { selectedId.value = id; await refreshHistory() }
function startEditing() {
  if (!history.value) return
  editName.value = history.value.customer.name
  editPhone.value = history.value.customer.phone
  editEmail.value = history.value.customer.email
  isEditing.value = true
}
async function saveCustomer() {
  if (!selectedId.value || !editName.value.trim() || isSaving.value) return
  isSaving.value = true
  try {
    const csrf = await $fetch<{ csrfToken: string }>(`${config.public.apiBase}/api/auth/csrf/`, { credentials: 'include' })
    await $fetch(`${config.public.apiBase}/api/sales/customers/${selectedId.value}/`, {
      method: 'PATCH', credentials: 'include', headers: { 'X-CSRFToken': csrf.csrfToken },
      body: { name: editName.value.trim(), phone: editPhone.value.trim(), email: editEmail.value.trim() }
    })
    isEditing.value = false
    await refreshHistory()
    await refreshCustomers()
  } finally {
    isSaving.value = false
  }
}
watch(search, refreshCustomers)
</script>

<template>
  <main class="customers-shell">
    <header><div><p class="eyebrow">Relacionamento</p><h1>Clientes</h1><p class="muted">Consulte clientes e o histórico de compras da organização.</p></div><nav><NuxtLink to="/pdv">Voltar ao PDV</NuxtLink><NuxtLink to="/relatorios">Relatórios</NuxtLink></nav></header>
    <section class="customers-layout">
      <aside class="customer-list"><label>Buscar cliente<input v-model="search" placeholder="Nome, telefone ou documento"></label><p v-if="loadingCustomers" class="muted">Buscando...</p><button v-for="customer in customers?.results || []" :key="customer.id" type="button" :class="{ selected: selectedId === customer.id }" @click="selectCustomer(customer.id)"><strong>{{ customer.name }}</strong><small>{{ customer.phone || customer.document || 'Sem contato' }} · {{ customer.sales_count }} venda(s)</small></button><p v-if="!loadingCustomers && !customers?.results.length" class="muted">Nenhum cliente encontrado.</p></aside>
      <section class="history-card"><p v-if="!selectedId" class="muted">Selecione um cliente para consultar o histórico.</p><p v-else-if="loadingHistory" class="muted">Carregando histórico...</p><template v-else-if="history"><div class="history-heading"><div><p class="eyebrow">Histórico</p><h2>{{ history.customer.name }}</h2></div><button type="button" @click="startEditing">Editar cadastro</button></div><div v-if="isEditing" class="edit-form"><label>Nome<input v-model="editName"></label><label>Telefone<input v-model="editPhone"></label><label>E-mail<input v-model="editEmail" type="email"></label><div><button type="button" :disabled="isSaving" @click="saveCustomer">{{ isSaving ? 'Salvando...' : 'Salvar' }}</button><button type="button" class="cancel" :disabled="isSaving" @click="isEditing = false">Cancelar</button></div></div><div class="metrics"><div><span>Total comprado</span><strong>{{ money(history.completed_total) }}</strong></div><div><span>Compras concluídas</span><strong>{{ history.completed_sales_count }}</strong></div></div><h3>Vendas</h3><ul><li v-for="sale in history.sales" :key="sale.id"><span>Venda #{{ sale.id }} · {{ sale.payment_method_label }}<small>{{ new Date(sale.created_at).toLocaleString('pt-BR') }}</small></span><strong>{{ money(sale.total_amount) }}</strong></li></ul></template></section>
    </section>
  </main>
</template>

<style scoped>
.customers-shell { min-height: 100vh; padding: 40px; background: #f8fafc; color: #0f172a; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
header, .customers-layout { max-width: 1080px; margin: 0 auto; } header { display: flex; justify-content: space-between; align-items: end; gap: 20px; } nav { display: flex; gap: 16px; flex-wrap: wrap; } a { color: #0369a1; font-weight: 800; } h1 { margin: 0; font-size: clamp(2rem, 5vw, 3.4rem); letter-spacing: -.05em; } h2 { margin-top: 0; } h3 { margin-top: 28px; }.eyebrow { margin: 0 0 8px; color: #0369a1; font-size: .75rem; font-weight: 900; letter-spacing: .12em; text-transform: uppercase; }.muted { color: #64748b; }.customers-layout { display: grid; grid-template-columns: minmax(240px, 340px) 1fr; gap: 18px; margin-top: 32px; }.customer-list, .history-card { display: grid; gap: 12px; align-content: start; padding: 20px; border: 1px solid #e2e8f0; border-radius: 18px; background: white; }label { display: grid; gap: 6px; color: #475569; font-weight: 800; }input { padding: 12px; border: 1px solid #cbd5e1; border-radius: 10px; font: inherit; }.customer-list button { display: grid; gap: 4px; padding: 12px; border: 1px solid #e2e8f0; border-radius: 10px; background: #f8fafc; text-align: left; cursor: pointer; }.customer-list button.selected { border-color: #0284c7; background: #e0f2fe; }.customer-list small, .metrics span, li small { color: #64748b; }.metrics { display: flex; gap: 14px; }.metrics div { display: grid; gap: 6px; flex: 1; padding: 14px; border-radius: 12px; background: #f0f9ff; }.metrics strong { font-size: 1.35rem; }ul { display: grid; gap: 10px; padding: 0; list-style: none; }li { display: flex; justify-content: space-between; gap: 16px; padding: 12px 0; border-bottom: 1px solid #f1f5f9; }li span { display: grid; gap: 4px; }li strong { white-space: nowrap; }@media (max-width: 720px) { .customers-shell { padding: 22px; } header, .customers-layout { display: grid; } }
.history-heading { display: flex; justify-content: space-between; align-items: start; gap: 16px; }.edit-form { display: grid; gap: 12px; padding: 16px; border-radius: 12px; background: #f8fafc; }.edit-form > div { display: flex; gap: 8px; }.cancel { background: #e2e8f0; color: #334155; }
</style>
