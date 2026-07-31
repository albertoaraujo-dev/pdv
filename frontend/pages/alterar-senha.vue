<script setup lang="ts">
definePageMeta({ middleware: 'auth' })

const config = useRuntimeConfig()

const currentPassword = ref('')
const newPassword = ref('')
const newPasswordConfirm = ref('')
const errorMessage = ref('')
const successMessage = ref('')
const isSubmitting = ref(false)
const isLoggingOut = ref(false)

const passwordRules = [
  'Use pelo menos 8 caracteres.',
  'Não use uma senha comum, como senha123 ou 12345678.',
  'Não use uma senha totalmente numérica.',
  'Evite senha parecida com seu nome, usuário ou e-mail.'
]

function getCookie(name: string) {
  return document.cookie
    .split('; ')
    .find((cookie) => cookie.startsWith(`${name}=`))
    ?.split('=')[1]
}

async function submitPasswordChange() {
  errorMessage.value = ''
  successMessage.value = ''
  isSubmitting.value = true

  try {
    const csrf = await $fetch<{ csrfToken: string }>(`${config.public.apiBase}/api/auth/csrf/`, {
      credentials: 'include'
    })

    await $fetch(`${config.public.apiBase}/api/auth/change-password/`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'X-CSRFToken': getCookie('csrftoken') || csrf.csrfToken
      },
      body: {
        current_password: currentPassword.value,
        new_password: newPassword.value,
        new_password_confirm: newPasswordConfirm.value
      }
    })

    currentPassword.value = ''
    newPassword.value = ''
    newPasswordConfirm.value = ''
    successMessage.value = 'Senha alterada com sucesso.'
  } catch (error: any) {
    errorMessage.value = error?.data?.detail || 'Não foi possível alterar a senha.'
  } finally {
    isSubmitting.value = false
  }
}

async function submitLogout() {
  errorMessage.value = ''
  successMessage.value = ''
  isLoggingOut.value = true

  try {
    const csrf = await $fetch<{ csrfToken: string }>(`${config.public.apiBase}/api/auth/csrf/`, {
      credentials: 'include'
    })

    await $fetch(`${config.public.apiBase}/api/auth/logout/`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'X-CSRFToken': getCookie('csrftoken') || csrf.csrfToken
      }
    })

    window.location.href = '/login'
  } catch (error: any) {
    errorMessage.value = error?.data?.detail || 'Não foi possível encerrar a sessão.'
  } finally {
    isLoggingOut.value = false
  }
}
</script>

<template>
  <main class="password-shell">
    <section class="password-card">
      <div class="header-row">
        <div>
          <p class="eyebrow">Segurança da conta</p>
          <h1>Alterar senha</h1>
        </div>
        <button class="logout-button" type="button" :disabled="isLoggingOut" @click="submitLogout">
          {{ isLoggingOut ? 'Saindo...' : 'Sair' }}
        </button>
      </div>

      <aside class="requirements">
        <strong>Sua nova senha precisa seguir estes critérios:</strong>
        <ul>
          <li v-for="rule in passwordRules" :key="rule">{{ rule }}</li>
        </ul>
      </aside>

      <form class="password-form" @submit.prevent="submitPasswordChange">
        <label>
          Senha atual
          <input v-model="currentPassword" type="password" autocomplete="current-password" required>
        </label>

        <label>
          Nova senha
          <input v-model="newPassword" type="password" autocomplete="new-password" minlength="8" required>
        </label>

        <label>
          Confirmar nova senha
          <input v-model="newPasswordConfirm" type="password" autocomplete="new-password" minlength="8" required>
        </label>

        <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
        <p v-if="successMessage" class="success">{{ successMessage }}</p>

        <button class="primary-button" type="submit" :disabled="isSubmitting">
          {{ isSubmitting ? 'Alterando...' : 'Alterar senha' }}
        </button>
      </form>
    </section>
  </main>
</template>

<style scoped>
.password-shell {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  background: #111827;
  color: #f8fafc;
  font-family: Inter, ui-sans-serif, system-ui, sans-serif;
}

.password-card {
  width: min(540px, 100%);
  display: grid;
  gap: 22px;
  padding: 32px;
  border-radius: 24px;
  background: #1f2937;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.32);
}

.header-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.eyebrow {
  margin: 0;
  color: #67e8f9;
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  font-size: 2.1rem;
}

.requirements {
  display: grid;
  gap: 10px;
  padding: 16px;
  border: 1px solid rgba(103, 232, 249, 0.22);
  border-radius: 16px;
  background: rgba(8, 47, 73, 0.35);
  color: #d1f7ff;
}

.requirements ul {
  margin: 0;
  padding-left: 20px;
  color: #d1d5db;
}

.requirements li + li {
  margin-top: 6px;
}

.password-form {
  display: grid;
  gap: 18px;
}

label {
  display: grid;
  gap: 8px;
  color: #d1d5db;
  font-weight: 700;
}

input {
  width: 100%;
  box-sizing: border-box;
  padding: 12px 14px;
  border: 1px solid #4b5563;
  border-radius: 12px;
  background: #111827;
  color: #f8fafc;
}

.primary-button,
.logout-button {
  padding: 13px 16px;
  border: 0;
  border-radius: 12px;
  font-weight: 900;
  cursor: pointer;
}

.primary-button {
  background: #67e8f9;
  color: #164e63;
}

.logout-button {
  background: rgba(248, 250, 252, 0.1);
  color: #f8fafc;
}

.primary-button:disabled,
.logout-button:disabled {
  cursor: wait;
  opacity: 0.7;
}

.error,
.success {
  margin: 0;
  padding: 10px 12px;
  border-radius: 12px;
}

.error {
  background: rgba(239, 68, 68, 0.14);
  color: #fecaca;
}

.success {
  background: rgba(34, 197, 94, 0.14);
  color: #bbf7d0;
}

@media (max-width: 520px) {
  .header-row {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
