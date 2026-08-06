export default defineNuxtRouteMiddleware(() => {
  const config = useRuntimeConfig()
  return navigateTo(`${config.public.apiBase}/admin/`, { external: true })
})
