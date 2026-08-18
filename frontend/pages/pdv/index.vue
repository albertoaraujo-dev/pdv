<script setup lang="ts">
definePageMeta({ middleware: 'pos-auth' })

const config = useRuntimeConfig()
const apiBase = config.public.apiBase

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

type CartItem = {
  product: Product
  quantity: number
}

type Sale = {
  id: number
  total_amount: string
  payment_method: string
  payment_method_label: string
  amount_received: string
  change_amount: string
  items: Array<{
    id: number
    product_name: string
    product_sku: string
    quantity: string
    unit_price: string
    line_total: string
  }>
}

const paymentMethods = [
  { value: 'cash', label: 'Dinheiro' },
  { value: 'card_external', label: 'Cartão externo' },
  { value: 'pix_manual', label: 'Pix manual' },
  { value: 'other', label: 'Outro' }
]

const { data: user, pending: isLoadingUser } = await useFetch<AuthUser>(`${apiBase}/api/auth/me/`, {
  credentials: 'include',
  server: false
})

const isLoggingOut = ref(false)
const isClosingSale = ref(false)
const isAddingSearchResult = ref(false)
const search = ref('')
const productQuery = ref('')
const cartItems = ref<CartItem[]>([])
const selectedStoreId = ref<number | null>(null)
const paymentMethod = ref('cash')
const amountReceived = ref('')
const saleError = ref('')
const saleSuccess = ref('')
const searchMessage = ref('')
const lastSale = ref<Sale | null>(null)
const searchInput = ref<HTMLInputElement | null>(null)
const displayName = computed(() => user.value?.name || user.value?.username || 'Usuário')
const storeNames = computed(() => user.value?.stores.map((store) => `${store.code} - ${store.name}`).join(', ') || 'Nenhuma loja ativa')
const selectedStore = computed(() => user.value?.stores.find((store) => store.id === selectedStoreId.value))
const cartTotal = computed(() => cartItems.value.reduce((total, item) => total + Number(item.product.price) * item.quantity, 0))
const cartItemCount = computed(() => cartItems.value.reduce((total, item) => total + item.quantity, 0))
const amountReceivedNumber = computed(() => Number(String(amountReceived.value).replace(',', '.')) || 0)
const amountToSend = computed(() => paymentMethod.value === 'cash' ? amountReceivedNumber.value : cartTotal.value)
const changeAmount = computed(() => Math.max(amountReceivedNumber.value - cartTotal.value, 0))
const remainingCashAmount = computed(() => Math.max(cartTotal.value - amountReceivedNumber.value, 0))
const hasEnoughPayment = computed(() => amountToSend.value >= cartTotal.value)
const paymentPendingMessage = computed(() => {
  if (!cartItems.value.length || paymentMethod.value !== 'cash' || hasEnoughPayment.value) {
    return ''
  }
  if (!amountReceived.value) {
    return 'Informe o valor recebido em dinheiro para finalizar a venda.'
  }
  return `O valor recebido em dinheiro ainda é menor que o total da venda. Faltam ${money(remainingCashAmount.value)}.`
})
const canCloseSale = computed(() => Boolean(selectedStoreId.value && cartItems.value.length && hasEnoughPayment.value && !isClosingSale.value))
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
  server: false,
  watch: [productUrl]
})

let searchTimeout: ReturnType<typeof setTimeout> | undefined
const isClient = ref(false)

onMounted(() => {
  isClient.value = true
  focusSearch()
})

function focusSearch() {
  nextTick(() => {
    window.setTimeout(() => searchInput.value?.focus({ preventScroll: true }), 0)
  })
}

watch(user, (value) => {
  if (!selectedStoreId.value && value?.stores.length === 1) {
    selectedStoreId.value = value.stores[0].id
  }
}, { immediate: true })

watch(search, (value) => {
  searchMessage.value = ''
  if (searchTimeout) {
    clearTimeout(searchTimeout)
  }
  searchTimeout = setTimeout(() => {
    productQuery.value = value.trim()
  }, 250)
})

watch(cartTotal, (value) => {
  if (!value) {
    amountReceived.value = ''
    return
  }
  if (paymentMethod.value !== 'cash') {
    amountReceived.value = value.toFixed(2)
  }
})

watch(paymentMethod, (value) => {
  saleError.value = ''
  saleSuccess.value = ''
  amountReceived.value = value !== 'cash' && cartTotal.value ? cartTotal.value.toFixed(2) : ''
})

watch([amountReceived, selectedStoreId], () => {
  saleError.value = ''
  saleSuccess.value = ''
})

async function logout() {
  if (isClosingSale.value) {
    return
  }

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

function addToCart(product: Product) {
  if (isClosingSale.value) {
    return
  }

  saleError.value = ''
  saleSuccess.value = ''
  searchMessage.value = ''
  lastSale.value = null
  const item = cartItems.value.find((cartItem) => cartItem.product.id === product.id)
  if (item) {
    item.quantity += 1
    focusSearch()
    return
  }
  cartItems.value.push({ product, quantity: 1 })
  focusSearch()
}

async function addSearchResultToCart() {
  if (isAddingSearchResult.value || isClosingSale.value) {
    return
  }
  const value = search.value.trim()
  if (!value) {
    searchMessage.value = 'Digite nome, SKU ou código de barras para buscar.'
    return
  }
  if (searchTimeout) {
    clearTimeout(searchTimeout)
  }

  isAddingSearchResult.value = true

  try {
    productQuery.value = value
    const params = new URLSearchParams({ q: value })
    const searchResults = await $fetch<PaginatedResponse<Product>>(`${config.public.apiBase}/api/catalog/products/?${params.toString()}`, {
      credentials: 'include'
    })

    const results = searchResults.results || []
    if (results.length === 1) {
      addToCart(results[0])
      search.value = ''
      productQuery.value = ''
      searchMessage.value = `${results[0].name} adicionado ao carrinho.`
      await refreshProducts()
      focusSearch()
      return
    }
    if (!results.length) {
      searchMessage.value = 'Nenhum produto encontrado para esta busca.'
      return
    }
    searchMessage.value = 'Mais de um produto encontrado. Escolha na lista.'
  } catch {
    searchMessage.value = 'Não foi possível buscar o produto. Tente novamente.'
  } finally {
    isAddingSearchResult.value = false
    focusSearch()
  }
}

function decrementItem(productId: number) {
  if (isClosingSale.value) {
    return
  }

  saleError.value = ''
  saleSuccess.value = ''
  lastSale.value = null
  const item = cartItems.value.find((cartItem) => cartItem.product.id === productId)
  if (!item) {
    return
  }
  if (item.quantity === 1) {
    saleError.value = 'A quantidade mínima é 1. Use Remover para excluir o item.'
    return
  }
  item.quantity -= 1
}

function removeItem(productId: number) {
  if (isClosingSale.value) {
    return
  }

  saleError.value = ''
  saleSuccess.value = ''
  lastSale.value = null
  cartItems.value = cartItems.value.filter((cartItem) => cartItem.product.id !== productId)
}

function updateItemQuantity(productId: number, value: string | number, input?: HTMLInputElement) {
  if (isClosingSale.value) {
    return
  }

  saleError.value = ''
  saleSuccess.value = ''
  lastSale.value = null
  const quantity = Number.parseInt(String(value), 10)
  const item = cartItems.value.find((cartItem) => cartItem.product.id === productId)
  if (!item) {
    return
  }
  if (!Number.isInteger(quantity) || quantity <= 0) {
    saleError.value = 'Quantidade não pode ser zero.'
    if (input) {
      input.value = String(item.quantity)
    }
    return
  }
  item.quantity = quantity
}

function getFetchErrorMessage(error: unknown) {
  if (typeof error === 'object' && error && 'data' in error) {
    const data = (error as { data?: { detail?: string, errors?: Record<string, string[] | string> } }).data
    if (data?.detail) {
      return data.detail
    }
    if (data?.errors) {
      const firstError = Object.values(data.errors)[0]
      if (Array.isArray(firstError)) {
        return firstError[0] || 'Não foi possível finalizar a venda.'
      }
      if (firstError) {
        return firstError
      }
    }
  }
  return 'Não foi possível finalizar a venda.'
}

function createClientRequestId() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

async function closeSale() {
  if (isClosingSale.value) {
    return
  }

  saleError.value = ''
  saleSuccess.value = ''

  if (!selectedStoreId.value) {
    saleError.value = 'Selecione uma loja para finalizar a venda.'
    return
  }
  if (!cartItems.value.length) {
    saleError.value = 'Adicione pelo menos um item ao carrinho.'
    return
  }
  if (!hasEnoughPayment.value) {
    saleError.value = 'O valor recebido não pode ser menor que o total da venda.'
    return
  }

  isClosingSale.value = true
  const clientRequestId = createClientRequestId()

  try {
    const csrf = await $fetch<{ csrfToken: string }>(`${config.public.apiBase}/api/auth/csrf/`, {
      credentials: 'include'
    })
    const sale = await $fetch<Sale>(`${config.public.apiBase}/api/sales/sales/`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'X-CSRFToken': csrf.csrfToken
      },
      body: {
        store: selectedStoreId.value,
        payment_method: paymentMethod.value,
        amount_received: amountToSend.value.toFixed(2),
        client_request_id: clientRequestId,
        items: cartItems.value.map((item) => ({
          product: item.product.id,
          quantity: item.quantity.toFixed(3)
        }))
      }
    })

    cartItems.value = []
    amountReceived.value = ''
    lastSale.value = sale
    saleSuccess.value = sale.change_amount !== '0.00'
      ? `Venda #${sale.id} finalizada em ${money(sale.total_amount)}. Troco: ${money(sale.change_amount)}.`
      : `Venda #${sale.id} finalizada em ${money(sale.total_amount)}.`
    await refreshProducts()
    focusSearch()
  } catch (error) {
    saleError.value = getFetchErrorMessage(error)
  } finally {
    isClosingSale.value = false
  }
}

function money(value: number | string) {
  return Number(value).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}
</script>

<template>
  <main class="pos-shell">
    <header class="pos-header">
      <div>
        <p class="eyebrow">Ponto de venda</p>
        <h1>PDV</h1>
      </div>

      <aside v-if="isClient && user" class="user-card" aria-label="Usuário logado">
        <span>Logado como</span>
        <strong>{{ displayName }}</strong>
        <small>{{ user.username }} · {{ user.profile.role_label }}</small>
        <button type="button" :class="{ 'button-loading': isLoggingOut }" :disabled="isLoggingOut || isClosingSale" @click="logout">
          {{ isLoggingOut ? 'Saindo...' : 'Sair do PDV' }}
        </button>
      </aside>
    </header>

    <section class="status-card">
      <p>Área reservada para o ponto de venda.</p>
      <dl v-if="isClient && user">
        <div>
          <dt>Organização</dt>
          <dd>{{ user.profile.organization_name }}</dd>
        </div>
        <div>
          <dt>Lojas liberadas</dt>
          <dd>{{ storeNames }}</dd>
        </div>
      </dl>

      <label v-if="isClient && user?.stores.length" class="store-field">
        Loja da venda
        <select v-model.number="selectedStoreId" :disabled="isClosingSale">
          <option :value="null" disabled>Selecione uma loja</option>
          <option v-for="store in user.stores" :key="store.id" :value="store.id">
            {{ store.code }} - {{ store.name }}
          </option>
        </select>
      </label>
    </section>

    <div class="pos-workspace">
      <section class="products-card">
        <div class="products-heading">
          <div>
            <p class="eyebrow">Catálogo</p>
            <h2>Produtos disponíveis</h2>
          </div>
          <button type="button" :disabled="!isClient || isLoadingProducts" @click="refreshProducts">
            Atualizar
          </button>
        </div>

        <label class="search-field">
          Buscar por nome, SKU ou código de barras
          <input ref="searchInput" v-model="search" type="search" :disabled="isAddingSearchResult || isClosingSale" placeholder="Ex.: água, SKU ou código" @keydown.enter.prevent="addSearchResultToCart">
        </label>
        <p v-if="isAddingSearchResult" class="muted">Buscando produto...</p>
        <p v-if="searchMessage" class="muted">{{ searchMessage }}</p>

        <p v-if="!isClient || isLoadingUser || isLoadingProducts" class="muted">Carregando produtos...</p>
        <p v-else-if="!products?.results.length" class="muted">Nenhum produto encontrado.</p>

        <ul v-else class="product-list">
          <li v-for="product in products.results" :key="product.id">
            <div>
              <strong>{{ product.name }}</strong>
              <small><span v-if="product.sku">SKU {{ product.sku }} · </span>{{ product.category.name }} · {{ product.unit.symbol }}</small>
            </div>
            <div class="product-actions">
              <span>{{ money(product.price) }}</span>
              <button type="button" :disabled="isClosingSale" @click="addToCart(product)">
                Adicionar
              </button>
            </div>
          </li>
        </ul>

        <small v-if="isClient && products" class="muted">{{ products.count }} produto(s) encontrado(s)</small>
      </section>

      <aside class="cart-card">
        <div>
          <p class="eyebrow">Carrinho</p>
          <h2>Venda atual</h2>
        </div>

        <p v-if="!cartItems.length" class="muted">Nenhum item adicionado.</p>

        <ul v-else class="cart-list">
          <li v-for="item in cartItems" :key="item.product.id">
            <div>
              <strong>{{ item.product.name }}</strong>
              <small>{{ item.quantity }} x {{ money(item.product.price) }}</small>
            </div>
            <div class="quantity-actions">
              <button type="button" :disabled="isClosingSale" @click="decrementItem(item.product.id)">-</button>
              <input class="quantity-input" type="number" min="1" step="1" :value="item.quantity" :disabled="isClosingSale" inputmode="numeric" aria-label="Quantidade" @change="updateItemQuantity(item.product.id, ($event.target as HTMLInputElement).value, $event.target as HTMLInputElement)">
              <button type="button" :disabled="isClosingSale" @click="addToCart(item.product)">+</button>
              <button type="button" :disabled="isClosingSale" @click="removeItem(item.product.id)">Remover</button>
            </div>
          </li>
        </ul>

      <div class="cart-total">
        <span>{{ cartItemCount }} item(ns)</span>
        <strong>{{ money(cartTotal) }}</strong>
      </div>

      <div class="payment-box">
        <label class="store-field">
          Forma de pagamento
          <select v-model="paymentMethod" :disabled="isClosingSale">
            <option v-for="method in paymentMethods" :key="method.value" :value="method.value">
              {{ method.label }}
            </option>
          </select>
        </label>

        <label class="store-field">
          Valor recebido
          <input v-model="amountReceived" :disabled="paymentMethod !== 'cash' || isClosingSale" inputmode="decimal" placeholder="0,00" @keydown.enter.prevent="closeSale">
        </label>

        <div v-if="paymentMethod === 'cash'" class="change-row">
          <span>Troco</span>
          <strong>{{ money(changeAmount) }}</strong>
        </div>
      </div>

      <p v-if="isClient && selectedStore" class="muted">Loja da venda: {{ selectedStore.code }} - {{ selectedStore.name }}</p>
      <p v-if="paymentPendingMessage" class="sale-message sale-message-warning">{{ paymentPendingMessage }}</p>
      <p v-if="saleError" class="sale-message sale-message-error">{{ saleError }}</p>
      <p v-if="saleSuccess" class="sale-message sale-message-success">{{ saleSuccess }}</p>

      <button type="button" class="close-sale-button" :class="{ 'button-loading': isClosingSale }" :disabled="!canCloseSale" @click="closeSale">
        {{ isClosingSale ? 'Finalizando...' : 'Finalizar venda' }}
      </button>

      <section v-if="lastSale" class="receipt-box" aria-label="Resumo da última venda">
        <div class="receipt-heading">
          <div>
            <p class="eyebrow">Resumo</p>
            <h3>Venda #{{ lastSale.id }}</h3>
          </div>
          <strong>{{ money(lastSale.total_amount) }}</strong>
        </div>

        <ul class="receipt-items">
          <li v-for="item in lastSale.items" :key="item.id">
            <span>{{ item.product_name }}</span>
            <small>{{ Number(item.quantity).toLocaleString('pt-BR') }} x {{ money(item.unit_price) }}</small>
            <strong>{{ money(item.line_total) }}</strong>
          </li>
        </ul>

        <dl class="receipt-totals">
          <div>
            <dt>Forma de pagamento</dt>
            <dd>{{ lastSale.payment_method_label }}</dd>
          </div>
          <div>
            <dt>Valor recebido</dt>
            <dd>{{ money(lastSale.amount_received) }}</dd>
          </div>
          <div>
            <dt>Troco</dt>
            <dd>{{ money(lastSale.change_amount) }}</dd>
          </div>
        </dl>
      </section>
      </aside>
    </div>
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
.products-card,
.cart-card {
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
  cursor: not-allowed;
  opacity: 0.65;
}

button.button-loading:disabled {
  cursor: wait;
}

.status-card {
  max-width: 760px;
  margin-bottom: 24px;
  padding: 24px;
}

.pos-workspace {
  display: grid;
  grid-template-columns: 1fr;
  align-items: start;
  gap: 24px;
}

.products-card {
  display: grid;
  gap: 18px;
  padding: 24px;
}

.cart-card {
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

.search-field,
.store-field {
  display: grid;
  gap: 8px;
  color: #475569;
  font-weight: 800;
}

input,
select {
  width: 100%;
  box-sizing: border-box;
  padding: 12px 14px;
  border: 1px solid #cbd5e1;
  border-radius: 12px;
  color: #0f172a;
}

.sale-message {
  margin: 0;
  padding: 12px 14px;
  border-radius: 12px;
  font-weight: 800;
}

.sale-message-error {
  border: 1px solid #fecaca;
  background: #fef2f2;
  color: #991b1b;
}

.sale-message-warning {
  border: 1px solid #fde68a;
  background: #fffbeb;
  color: #92400e;
}

.sale-message-success {
  border: 1px solid #bbf7d0;
  background: #f0fdf4;
  color: #166534;
}

.close-sale-button {
  width: 100%;
  justify-content: center;
  padding: 14px 18px;
  background: #0369a1;
}

.close-sale-button:disabled:not(.button-loading) {
  cursor: not-allowed !important;
}

.close-sale-button:disabled {
  cursor: not-allowed;
}

.close-sale-button.button-loading:disabled {
  cursor: wait !important;
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

.product-list strong,
.product-list small {
  display: block;
}

.product-list strong {
  margin-bottom: 4px;
}

.product-actions,
.quantity-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.product-list span,
.cart-total strong {
  font-weight: 900;
  white-space: nowrap;
}

.cart-list {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.cart-list li {
  display: grid;
  gap: 10px;
  padding: 14px 16px;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  background: #f8fafc;
}

.cart-list small {
  color: #64748b;
}

.receipt-box {
  display: grid;
  gap: 16px;
  padding: 18px;
  border: 1px dashed #94a3b8;
  border-radius: 16px;
  background: #f8fafc;
}

.receipt-heading,
.receipt-items li,
.receipt-totals div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.receipt-heading h3 {
  margin: 0;
  font-size: 1.25rem;
}

.receipt-items {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.receipt-items li {
  padding-bottom: 10px;
  border-bottom: 1px solid #e2e8f0;
}

.receipt-items span,
.receipt-items small {
  display: block;
}

.receipt-items small {
  color: #64748b;
}

.receipt-totals {
  gap: 10px;
}

.payment-box {
  display: grid;
  gap: 14px;
  padding: 16px;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  background: #f8fafc;
}

.change-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  color: #0f172a;
  font-weight: 900;
}

.quantity-actions button {
  margin-top: 0;
}

.quantity-input {
  width: 72px;
  padding: 9px 10px;
  text-align: center;
  font-weight: 800;
}

.cart-total {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-top: 16px;
  border-top: 1px solid #e2e8f0;
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

@media (min-width: 1100px) {
  .status-card {
    max-width: 820px;
  }

  .pos-workspace {
    grid-template-columns: minmax(0, 1fr) minmax(380px, 460px);
  }

  .cart-card {
    position: sticky;
    top: 24px;
  }
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
