export default defineNuxtRouteMiddleware(async (to) => {
  if (import.meta.server) return

  const config = useRuntimeConfig()

  try {
    const user = await $fetch<{ permissions: { can_access_admin: boolean } }>(`${config.public.apiBase}/api/auth/me/`, {
      credentials: 'include'
    })

    if (!user.permissions.can_access_admin) {
      return navigateTo(`/login?next=${encodeURIComponent(to.fullPath)}`)
    }

    return navigateTo(`${config.public.apiBase}/admin/`, { external: true })
  } catch {
    return navigateTo(`/login?next=${encodeURIComponent(to.fullPath)}`)
  }
})
