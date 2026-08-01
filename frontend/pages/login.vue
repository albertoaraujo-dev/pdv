<script setup lang="ts">
const config = useRuntimeConfig()
const route = useRoute()

const username = ref('')
const password = ref('')
const errorMessage = ref('')
const isSubmitting = ref(false)

type AuthUser = {
  permissions: {
    can_access_admin: boolean
    can_access_pos: boolean
    must_change_password: boolean
  }
}

async function submitLogin() {
  errorMessage.value = ''
  isSubmitting.value = true

  try {
    const csrf = await $fetch<{ csrfToken: string }>(`${config.public.apiBase}/api/auth/csrf/`, {
      credentials: 'include'
    })

    const user = await $fetch<AuthUser>(`${config.public.apiBase}/api/auth/login/`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'X-CSRFToken': csrf.csrfToken
      },
      body: {
        username: username.value,
        password: password.value
      }
    })

    const next = typeof route.query.next === 'string' ? route.query.next : null
    if (user.permissions.must_change_password) {
      await navigateTo('/alterar-senha')
      return
    }

    if (next?.startsWith('/admin')) {
      if (!user.permissions.can_access_admin) {
        errorMessage.value = 'Seu usuário não tem acesso ao painel administrativo.'
        return
      }
      await navigateTo(`${config.public.apiBase}/admin/`, { external: true })
      return
    }

    if (next?.startsWith('/pdv')) {
      if (!user.permissions.can_access_pos) {
        errorMessage.value = 'Seu usuário não tem acesso ao PDV. Verifique se o perfil possui uma loja ativa vinculada.'
        return
      }
      await navigateTo(next)
      return
    }

    if (user.permissions.can_access_admin) {
      await navigateTo(`${config.public.apiBase}/admin/`, { external: true })
      return
    }

    if (user.permissions.can_access_pos) {
      await navigateTo('/pdv')
      return
    }

    errorMessage.value = 'Login realizado, mas seu usuário ainda não tem acesso a uma área do sistema.'
  } catch (error: any) {
    errorMessage.value = error?.data?.detail || 'Não foi possível entrar com essas credenciais.'
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <main class="login-shell">
    <form class="login-card" @submit.prevent="submitLogin">
      <p class="eyebrow">Acesso seguro</p>
      <h1>Entrar</h1>

      <label>
        Usuário
        <input v-model="username" name="username" autocomplete="username" required>
      </label>

      <label>
        Senha
        <input v-model="password" name="password" type="password" autocomplete="current-password" required>
      </label>

      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>

      <button type="submit" :disabled="isSubmitting">
        {{ isSubmitting ? 'Entrando...' : 'Entrar' }}
      </button>
    </form>
  </main>
</template>

<style scoped>
.login-shell {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  background: #101828;
  color: #f8fafc;
  font-family: Inter, ui-sans-serif, system-ui, sans-serif;
}

.login-card {
  width: min(420px, 100%);
  display: grid;
  gap: 18px;
  padding: 32px;
  border-radius: 24px;
  background: #182234;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.32);
}

.eyebrow {
  margin: 0;
  color: #38bdf8;
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  font-size: 2.2rem;
}

label {
  display: grid;
  gap: 8px;
  color: #cbd5e1;
  font-weight: 700;
}

input {
  width: 100%;
  box-sizing: border-box;
  padding: 12px 14px;
  border: 1px solid #334155;
  border-radius: 12px;
  background: #0f172a;
  color: #f8fafc;
}

button {
  padding: 13px 16px;
  border: 0;
  border-radius: 12px;
  background: #38bdf8;
  color: #082f49;
  font-weight: 900;
  cursor: pointer;
}

button:disabled {
  cursor: wait;
  opacity: 0.7;
}

.error {
  margin: 0;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(239, 68, 68, 0.14);
  color: #fecaca;
}
</style>
