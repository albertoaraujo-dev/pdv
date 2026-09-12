<script setup lang="ts">
definePageMeta({ middleware: 'auth' })
type Store = { id: number, name: string, code: string }
type Sale = { id: number, store: number, status: string, total_amount: string, payment_method_label: string, customer: number | null, created_at: string }
type User = { stores: Store[] }
const config = useRuntimeConfig()
const { data: user } = await useFetch<User>(`${config.public.apiBase}/api/auth/me/`, { credentials: 'include', server: false })
const store = ref<number | null>(null)
const status = ref('')
const payment = ref('')
const dateFrom = ref('')
const dateTo = ref('')
const sales = ref<Sale[]>([])
const page = ref(1)
const total = ref(0)
const hasNext = ref(false)
const hasPrevious = ref(false)
const loading = ref(false)
const error = ref('')
const exportUrl = computed(() => {
  const params = new URLSearchParams()
  if (store.value) params.set('store', String(store.value)); if (status.value) params.set('status', status.value); if (payment.value) params.set('payment_method', payment.value); if (dateFrom.value) params.set('date_from', dateFrom.value); if (dateTo.value) params.set('date_to', dateTo.value)
  return `${config.public.apiBase}/api/sales/sales/export/?${params}`
})
function money(value: string) { return Number(value || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }) }
async function loadSales() {
  loading.value = true; error.value = ''
  const params = new URLSearchParams()
  params.set('page', String(page.value));
  if (store.value) params.set('store', String(store.value)); if (status.value) params.set('status', status.value); if (payment.value) params.set('payment_method', payment.value); if (dateFrom.value) params.set('date_from', dateFrom.value); if (dateTo.value) params.set('date_to', dateTo.value)
  try { const result = await $fetch<{ count: number, next: string | null, previous: string | null, results: Sale[] }>(`${config.public.apiBase}/api/sales/sales/?${params}`, { credentials: 'include' }); sales.value = result.results || []; total.value = result.count; hasNext.value = Boolean(result.next); hasPrevious.value = Boolean(result.previous) } catch { error.value = 'Nao foi possivel carregar as vendas.' } finally { loading.value = false }
}
function changePage(nextPage: number) { page.value = nextPage; loadSales() }
function applyFilters() { page.value = 1; loadSales() }
onMounted(loadSales)
</script>
<template>
  <main class="sales-shell"><header><div><p class="eyebrow">Operação</p><h1>Vendas</h1><p class="muted">{{ total }} venda(s) encontrada(s).</p></div><nav><NuxtLink to="/pdv">PDV</NuxtLink><NuxtLink to="/relatorios">Relatórios</NuxtLink></nav></header><section class="filters"><label>Loja<select v-model.number="store"><option :value="null">Todas</option><option v-for="item in user?.stores || []" :key="item.id" :value="item.id">{{ item.code }} - {{ item.name }}</option></select></label><label>Status<select v-model="status"><option value="">Todos</option><option value="completed">Concluída</option><option value="cancelled">Cancelada</option><option value="pending_payment">Pendente</option></select></label><label>Pagamento<select v-model="payment"><option value="">Todos</option><option value="cash">Dinheiro</option><option value="card_external">Cartão</option><option value="pix_manual">Pix manual</option></select></label><label>De<input v-model="dateFrom" type="date"></label><label>Até<input v-model="dateTo" type="date"></label><button type="button" :disabled="loading" @click="applyFilters">{{ loading ? 'Carregando...' : 'Filtrar' }}</button><a class="export" :href="exportUrl">Exportar CSV</a></section><p v-if="error" class="error">{{ error }}</p><p v-else-if="loading" class="muted">Carregando vendas...</p><section v-else class="sales-card"><p v-if="!sales.length" class="muted">Nenhuma venda encontrada.</p><ul v-else><li v-for="sale in sales" :key="sale.id"><span><strong>Venda #{{ sale.id }}</strong><small>{{ new Date(sale.created_at).toLocaleString('pt-BR') }} · {{ sale.payment_method_label }}</small></span><span><strong>{{ money(sale.total_amount) }}</strong><small>{{ sale.status === 'completed' ? 'Concluída' : sale.status }}</small></span></li></ul><div class="pagination"><button type="button" :disabled="!hasPrevious || loading" @click="changePage(page - 1)">Anterior</button><span>Página {{ page }}</span><button type="button" :disabled="!hasNext || loading" @click="changePage(page + 1)">Próxima</button></div></section></main>
</template>
<style scoped>
.sales-shell { min-height: 100vh; padding: 40px; background: #f8fafc; color: #0f172a; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }header, .filters, .sales-card { max-width: 1080px; margin: 0 auto; }header { display:flex; justify-content:space-between; align-items:end; gap:20px; }nav { display:flex; gap:16px; }a { color:#0369a1; font-weight:800; }.export { padding:11px 16px; border-radius:10px; background:#e0f2fe; text-decoration:none; }h1 { margin:0; font-size:clamp(2rem,5vw,3.4rem); letter-spacing:-.05em; }.eyebrow { margin:0 0 8px; color:#0369a1; font-size:.75rem; font-weight:900; letter-spacing:.12em; text-transform:uppercase; }.muted { color:#64748b; }.filters { display:flex; align-items:end; flex-wrap:wrap; gap:12px; margin-top:32px; padding:18px; border:1px solid #dbeafe; border-radius:18px; background:white; }label { display:grid; gap:6px; flex:1 1 140px; color:#475569; font-size:.85rem; font-weight:800; }input, select { width:100%; box-sizing:border-box; padding:11px; border:1px solid #cbd5e1; border-radius:10px; background:white; font:inherit; }button { padding:11px 16px; border:0; border-radius:10px; background:#0369a1; color:white; font:inherit; font-weight:800; }button:disabled { opacity:.45; }.sales-card { margin-top:18px; padding:20px; border:1px solid #e2e8f0; border-radius:18px; background:white; }ul { display:grid; gap:4px; padding:0; list-style:none; }li { display:flex; justify-content:space-between; gap:20px; padding:14px 0; border-bottom:1px solid #f1f5f9; }li span { display:grid; gap:4px; }li small { color:#64748b; }.pagination { display:flex; justify-content:center; align-items:center; gap:18px; margin-top:18px; }.error { max-width:1080px; margin:20px auto; color:#b91c1c; font-weight:800; }@media(max-width:720px){.sales-shell{padding:22px}header{display:grid}.filters{display:grid;align-items:stretch}li{display:grid}}
</style>
