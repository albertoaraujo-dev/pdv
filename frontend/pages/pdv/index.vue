<script setup lang="ts">
definePageMeta({ middleware: 'pos-auth' })

const config = useRuntimeConfig()
const apiBase = import.meta.server ? config.apiBaseServer : config.public.apiBase
const headers = import.meta.server ? useRequestHeaders(['cookie']) : undefined

type AuthUser = {
  username: string
  name: string
  profile: {
    role_label: string | null
    organization_name: string | null
  }
  stores: Array<{ id: number, name: string, code: string }>
}

type Product = {
  id: number
  name: string
  sku: string
  barcode: string
  price: string
  category: { name: string }
  unit: { symbol: string }
}

type PaginatedResponse<T> = {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

const { data: user } = await useFetch<AuthUser>(`${apiBase}/api/auth/me/`, {
  credentials: 'include',
  headers
})

const isLoggingOut = ref(false)
const search = ref('')
const productQuery = ref('')
const displayName = computed(() => user.value?.name || user.value?.username || 'Usuário')
const storeNames = computed(() => user.value?.stores.map((store) => `${store.code} - ${store.name}`).join(', ') || 'Nenhuma loja ativa')
const productUrl = computed(() => {
  const params = new URLSearchParams()
  if (productQuery.value) {
    params.set('q', productQuery.value)
  }
  const query = params.toString()
  return `${apiBase}/api/catalog/products/${query ? `?${query}` : ''}`
})

const { data: products, pending: isLoadingProducts, refresh: refreshProducts } = await useFetch<PaginatedResponse<Product>>(productUrl, {
  credentials: 'include',
  headers,
  watch: [productUrl]
})

let searchTimeout: ReturnType<typeof setTimeout> | undefined

watch(search, (value) => {
  if (searchTimeout) {
    clearTimeout(searchTimeout)
  }
  searchTimeout = setTimeout(() => {
    productQuery.value = value.trim()
  }, 250)
})

async function logout() {
  isLoggingOut.value = true

  try {
    const csrf = await $fetch<{ csrfToken: string }>(`${config.public.apiBase}/api/auth/csrf/`, {
      credentials: 'include'
    })

    await $fetch(`${config.public.apiBase}/api/auth/logout/`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'X-CSRFToken': csrf.csrfToken
      }
    })
  } finally {
    await navigateTo('/login?next=/pdv', { external: true })
  }
}
</script>

<template>
  <main class="pos-shell">
    <header class="pos-header">
      <div>
        <p class="eyebrow">Ponto de venda</p>
        <h1>PDV</h1>
      </div>

      <aside v-if="user" class="user-card" aria-label="Usuário logado">
        <span>Logado como</span>
        <strong>{{ displayName }}</strong>
        <small>{{ user.username }} · {{ user.profile.role_label }}</small>
        <button type="button" :disabled="isLoggingOut" @click="logout">
          {{ isLoggingOut ? 'Saindo...' : 'Sair do PDV' }}
        </button>
      </aside>
    </header>

    <section class="status-card">
      <p>Área reservada para o ponto de venda.</p>
      <dl v-if="user">
        <div>
          <dt>Organização</dt>
          <dd>{{ user.profile.organization_name }}</dd>
        </div>
        <div>
          <dt>Lojas liberadas</dt>
          <dd>{{ storeNames }}</dd>
        </div>
      </dl>
    </section>

    <section class="products-card">
      <div class="products-heading">
        <div>
          <p class="eyebrow">Catálogo</p>
          <h2>Produtos disponíveis</h2>
        </div>
        <button type="button" :disabled="isLoadingProducts" @click="refreshProducts">
          Atualizar
        </button>
      </div>

      <label class="search-field">
        Buscar por nome, SKU ou código de barras
        <input v-model="search" type="search" placeholder="Ex.: água, SKU ou código">
      </label>

      <p v-if="isLoadingProducts" class="muted">Carregando produtos...</p>
      <p v-else-if="!products?.results.length" class="muted">Nenhum produto encontrado.</p>

      <ul v-else class="product-list">
        <li v-for="product in products.results" :key="product.id">
          <div>
            <strong>{{ product.name }}</strong>
            <small>{{ product.sku }} · {{ product.category.name }} · {{ product.unit.symbol }}</small>
          </div>
          <span>R$ {{ product.price }}</span>
        </li>
      </ul>

      <small v-if="products" class="muted">{{ products.count }} produto(s) encontrado(s)</small>
    </section>
  </main>
</template>

<style scoped>
.pos-shell {
  min-height: 100vh;
  padding: 32px;
  background: #f8fafc;
  color: #0f172a;
  font-family: Inter, ui-sans-serif, system-ui, sans-serif;
}

.pos-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 24px;
}

.eyebrow {
  margin: 0 0 6px;
  color: #0369a1;
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  font-size: clamp(2rem, 4vw, 3.5rem);
}

.user-card,
.status-card,
.products-card {
  border: 1px solid #e2e8f0;
  border-radius: 20px;
  background: #ffffff;
  box-shadow: 0 18px 48px rgba(15, 23, 42, 0.08);
}

.user-card {
  min-width: min(320px, 100%);
  display: grid;
  gap: 4px;
  padding: 16px 18px;
}

.user-card span,
.user-card small,
dt {
  color: #64748b;
  font-size: 0.85rem;
  font-weight: 700;
}

.user-card strong {
  font-size: 1.15rem;
}

button {
  width: fit-content;
  margin-top: 8px;
  padding: 9px 12px;
  border: 0;
  border-radius: 10px;
  background: #0f172a;
  color: #ffffff;
  font-weight: 800;
  cursor: pointer;
}

button:disabled {
  cursor: wait;
  opacity: 0.65;
}

.status-card {
  max-width: 760px;
  margin-bottom: 24px;
  padding: 24px;
}

.products-card {
  max-width: 960px;
  display: grid;
  gap: 18px;
  padding: 24px;
}

.products-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

h2 {
  margin: 0;
  font-size: 1.8rem;
}

.search-field {
  display: grid;
  gap: 8px;
  color: #475569;
  font-weight: 800;
}

input {
  width: 100%;
  box-sizing: border-box;
  padding: 12px 14px;
  border: 1px solid #cbd5e1;
  border-radius: 12px;
  color: #0f172a;
}

.product-list {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.product-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  background: #f8fafc;
}

.product-list small,
.muted {
  color: #64748b;
}

.product-list span {
  font-weight: 900;
  white-space: nowrap;
}

.status-card p {
  margin: 0 0 18px;
}

dl {
  display: grid;
  gap: 16px;
  margin: 0;
}

dd {
  margin: 4px 0 0;
  font-weight: 800;
}

@media (max-width: 720px) {
  .pos-shell {
    padding: 20px;
  }

  .pos-header {
    display: grid;
  }
}
</style>
