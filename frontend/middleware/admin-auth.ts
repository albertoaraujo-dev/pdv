export default defineNuxtRouteMiddleware(async (to) => {
  const config = useRuntimeConfig()
  const apiBase = import.meta.server ? config.apiBaseServer : config.public.apiBase
  const headers = import.meta.server ? useRequestHeaders(['cookie']) : undefined

  try {
    const user = await $fetch<{ permissions: { can_access_admin: boolean; must_change_password: boolean } }>(`${apiBase}/api/auth/me/`, {
      credentials: 'include',
      headers
    })

    if (user.permissions.must_change_password) {
      return navigateTo('/alterar-senha')
    }

    if (!user.permissions.can_access_admin) {
      return navigateTo(`/login?next=${encodeURIComponent(to.fullPath)}`)
    }

    return navigateTo(`${config.public.apiBase}/admin/`, { external: true })
  } catch {
    return navigateTo(`/login?next=${encodeURIComponent(to.fullPath)}`)
  }
})
