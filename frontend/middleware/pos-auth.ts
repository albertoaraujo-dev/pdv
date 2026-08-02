export default defineNuxtRouteMiddleware(async (to) => {
  const config = useRuntimeConfig()
  const apiBase = import.meta.server ? config.apiBaseServer : config.public.apiBase
  const headers = import.meta.server ? useRequestHeaders(['cookie']) : undefined

  try {
    const user = await $fetch<{ permissions: { can_access_pos: boolean; must_change_password: boolean } }>(`${apiBase}/api/auth/me/`, {
      credentials: 'include',
      headers
    })

    if (user.permissions.must_change_password) {
      return navigateTo('/alterar-senha')
    }

    if (!user.permissions.can_access_pos) {
      return navigateTo(`/login?next=${encodeURIComponent(to.fullPath)}`)
    }
  } catch (error: any) {
    const reason = error?.data?.detail === 'Usuário inativo.' ? '&reason=inactive' : ''
    return navigateTo(`/login?next=${encodeURIComponent(to.fullPath)}${reason}`)
  }
})
