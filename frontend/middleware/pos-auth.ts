export default defineNuxtRouteMiddleware(async (to) => {
  if (import.meta.server) return

  const config = useRuntimeConfig()

  try {
    const user = await $fetch<{ permissions: { can_access_pos: boolean } }>(`${config.public.apiBase}/api/auth/me/`, {
      credentials: 'include'
    })

    if (!user.permissions.can_access_pos) {
      return navigateTo(`/login?next=${encodeURIComponent(to.fullPath)}`)
    }
  } catch {
    return navigateTo(`/login?next=${encodeURIComponent(to.fullPath)}`)
  }
})
