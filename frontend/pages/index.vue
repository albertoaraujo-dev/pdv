<script setup lang="ts">
const config = useRuntimeConfig()
</script>

<template>
  <main class="shell">
    <section class="hero">
      <p class="eyebrow">Base local ativa</p>
      <h1>{{ config.public.appName }}</h1>
      <p class="lead">ERP + PDV com Nuxt 4, Django, PostgreSQL e Redis.</p>
      <div class="links">
        <a href="http://localhost:8000/health/">Health backend</a>
        <NuxtLink to="/pdv">Abrir PDV</NuxtLink>
        <a :href="`${config.public.apiBase}/admin/`">Abrir painel</a>
      </div>
    </section>
  </main>
</template>

<style scoped>
.shell {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  background: #0f172a;
  color: #f8fafc;
  font-family: Inter, ui-sans-serif, system-ui, sans-serif;
}

.hero {
  width: min(720px, 100%);
  padding: 48px;
  border: 1px solid rgba(148, 163, 184, 0.3);
  border-radius: 28px;
  background: linear-gradient(135deg, rgba(15, 23, 42, 0.95), rgba(30, 41, 59, 0.88));
  box-shadow: 0 24px 80px rgba(2, 6, 23, 0.45);
}

.eyebrow {
  margin: 0 0 12px;
  color: #38bdf8;
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  font-size: clamp(2.4rem, 7vw, 5rem);
  line-height: 0.95;
}

.lead {
  margin: 20px 0 0;
  color: #cbd5e1;
  font-size: 1.15rem;
}

.links {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 32px;
}

a {
  padding: 12px 16px;
  border-radius: 999px;
  background: #f8fafc;
  color: #0f172a;
  font-weight: 800;
  text-decoration: none;
}
</style>
