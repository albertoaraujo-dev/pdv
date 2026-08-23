<script setup lang="ts">
const config = useRuntimeConfig()
const route = useRoute()
const identifier = ref('')
const newPassword = ref('')
const newPasswordConfirm = ref('')
const message = ref('')
const errorMessage = ref('')
const isSubmitting = ref(false)
const hasToken = computed(() => typeof route.query.uid === 'string' && typeof route.query.token === 'string')

async function submitRequest() {
  errorMessage.value = ''
  message.value = ''
  isSubmitting.value = true
  try {
    const csrf = await $fetch<{ csrfToken: string }>(`${config.public.apiBase}/api/auth/csrf/`, { credentials: 'include' })
    await $fetch(`${config.public.apiBase}/api/auth/password-reset/`, {
      method: 'POST', credentials: 'include', headers: { 'X-CSRFToken': csrf.csrfToken }, body: { identifier: identifier.value }
    })
    message.value = 'Se os dados corresponderem a uma conta, enviaremos as instruções por e-mail.'
  } catch {
    message.value = 'Se os dados corresponderem a uma conta, enviaremos as instruções por e-mail.'
  } finally {
    isSubmitting.value = false
  }
}

async function submitReset() {
  errorMessage.value = ''
  message.value = ''
  isSubmitting.value = true
  try {
    const csrf = await $fetch<{ csrfToken: string }>(`${config.public.apiBase}/api/auth/csrf/`, { credentials: 'include' })
    await $fetch(`${config.public.apiBase}/api/auth/password-reset/confirm/`, {
      method: 'POST', credentials: 'include', headers: { 'X-CSRFToken': csrf.csrfToken }, body: {
        uid: route.query.uid,
        token: route.query.token,
        new_password: newPassword.value,
        new_password_confirm: newPasswordConfirm.value
      }
    })
    message.value = 'Senha redefinida. Você já pode entrar com a nova senha.'
  } catch (error: any) {
    errorMessage.value = error?.data?.detail || 'Não foi possível redefinir a senha.'
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <main class="reset-shell">
    <form class="reset-card" @submit.prevent="hasToken ? submitReset() : submitRequest()">
      <p class="eyebrow">Acesso seguro</p>
      <h1>{{ hasToken ? 'Criar nova senha' : 'Redefinir senha' }}</h1>
      <template v-if="!hasToken">
        <p>Informe seu usuário ou e-mail. Se houver uma conta correspondente, enviaremos um link.</p>
        <label>Usuário ou e-mail<input v-model="identifier" autocomplete="username" required></label>
      </template>
      <template v-else>
        <label>Nova senha<input v-model="newPassword" type="password" autocomplete="new-password" required></label>
        <label>Confirme a nova senha<input v-model="newPasswordConfirm" type="password" autocomplete="new-password" required></label>
      </template>
      <p v-if="message" class="message">{{ message }}</p>
      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
      <button type="submit" :disabled="isSubmitting">{{ isSubmitting ? 'Processando...' : hasToken ? 'Salvar nova senha' : 'Enviar instruções' }}</button>
      <NuxtLink class="back-link" to="/login">Voltar para o login</NuxtLink>
    </form>
  </main>
</template>

<style scoped>
.reset-shell { min-height: 100vh; display: grid; place-items: center; padding: 24px; background: #101828; color: #f8fafc; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
.reset-card { width: min(440px, 100%); display: grid; gap: 18px; padding: 32px; border-radius: 24px; background: #182234; box-shadow: 0 24px 80px rgba(0, 0, 0, .32); }
.eyebrow { margin: 0; color: #38bdf8; font-size: .78rem; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }
h1 { margin: 0; font-size: 2rem; }
p { color: #cbd5e1; line-height: 1.5; }
label { display: grid; gap: 8px; color: #cbd5e1; font-weight: 700; }
input { box-sizing: border-box; width: 100%; padding: 12px 14px; border: 1px solid #334155; border-radius: 12px; background: #0f172a; color: #f8fafc; }
button { padding: 13px 16px; border: 0; border-radius: 12px; background: #38bdf8; color: #082f49; font-weight: 900; cursor: pointer; }
button:disabled { cursor: wait; opacity: .7; }
.message, .error { margin: 0; padding: 10px 12px; border-radius: 12px; }
.message { background: rgba(34, 197, 94, .14); color: #bbf7d0; }
.error { background: rgba(239, 68, 68, .14); color: #fecaca; }
.back-link { color: #bae6fd; text-align: center; text-decoration: none; }
</style>
