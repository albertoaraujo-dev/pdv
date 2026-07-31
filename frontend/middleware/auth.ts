export default defineNuxtRouteMiddleware(async (to) => {
  const config = useRuntimeConfig()
  const apiBase = import.meta.server ? config.apiBaseServer : config.public.apiBase
  const headers = import.meta.server ? useRequestHeaders(['cookie']) : undefined

  try {
    await $fetch(`${apiBase}/api/auth/me/`, {
      credentials: 'include',
      headers
    })
  } catch {
    return navigateTo(`/login?next=${encodeURIComponent(to.fullPath)}`)
  }
})
