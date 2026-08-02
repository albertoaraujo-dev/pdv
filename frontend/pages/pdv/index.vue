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

const { data: user } = await useFetch<AuthUser>(`${apiBase}/api/auth/me/`, {
  credentials: 'include',
  headers
})

const displayName = computed(() => user.value?.name || user.value?.username || 'Usuário')
const storeNames = computed(() => user.value?.stores.map((store) => `${store.code} - ${store.name}`).join(', ') || 'Nenhuma loja ativa')
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
.status-card {
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

.status-card {
  max-width: 760px;
  padding: 24px;
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
