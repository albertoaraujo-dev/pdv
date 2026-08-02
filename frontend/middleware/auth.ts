export default defineNuxtRouteMiddleware(async (to) => {
  const config = useRuntimeConfig()
  const apiBase = import.meta.server ? config.apiBaseServer : config.public.apiBase
  const headers = import.meta.server ? useRequestHeaders(['cookie']) : undefined

  try {
    await $fetch(`${apiBase}/api/auth/me/`, {
      credentials: 'include',
      headers
    })
  } catch (error: any) {
    const reason = error?.data?.detail === 'Usuário inativo.' ? '&reason=inactive' : ''
    return navigateTo(`/login?next=${encodeURIComponent(to.fullPath)}${reason}`)
  }
})
