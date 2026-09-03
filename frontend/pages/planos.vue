<script setup lang="ts">
import type { BillingCatalogModule } from '~/types/billing'

const { data: plans, pending, error, refresh } = useBillingPlans()

const hasError = computed(() => Boolean(error.value))

function formatPrice(value: string) {
  const amount = Number(value)
  return Number.isNaN(amount)
    ? value
    : amount.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatLimitKey(key: string) {
  return key.replaceAll('_', ' ')
}

function formatLimit(value: unknown) {
  if (value === null) return 'sem limite'
  if (typeof value === 'boolean') return value ? 'sim' : 'não'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function moduleLabel(module: BillingCatalogModule) {
  if (module.is_base || module.is_free) return 'Base / grátis'
  return 'PLUS'
}

function modulePrice(module: BillingCatalogModule) {
  if (module.is_base || module.is_free || Number(module.monthly_price) === 0) return 'Incluído'
  return `+ R$ ${formatPrice(module.monthly_price)}/mês`
}

function dependencyNames(module: BillingCatalogModule) {
  return module.dependencies.length ? module.dependencies.join(', ') : ''
}
</script>

<template>
  <main class="plans-shell">
    <header class="plans-header">
      <NuxtLink class="brand" to="/">PDV Final</NuxtLink>
      <NuxtLink class="back-link" to="/">Voltar ao início</NuxtLink>
    </header>

    <section class="intro" aria-labelledby="plans-title">
      <p class="eyebrow">Planos transparentes</p>
      <h1 id="plans-title">Escolha a base para sua operação.</h1>
      <p class="intro-copy">Comece com o essencial e adicione capacidade quando seu negócio precisar. Esta página é apenas informativa: a contratação ainda não é feita por aqui.</p>
    </section>

    <section class="foundation" aria-labelledby="foundation-title">
      <div class="foundation-mark">01</div>
      <div>
        <p class="eyebrow">O que já vem na base</p>
        <h2 id="foundation-title">Core e catálogo são gratuitos.</h2>
        <p>O <strong>core</strong> sustenta a conta e a organização. O <strong>catálogo</strong> mantém produtos e preços. O <strong>sales</strong> é o primeiro módulo comercializável e depende do catálogo para funcionar.</p>
      </div>
    </section>

    <div v-if="pending" class="state-panel" role="status">
      <span class="loader" aria-hidden="true" />
      <div><strong>Carregando planos</strong><p>Buscando as opções disponíveis agora.</p></div>
    </div>
    <div v-else-if="hasError" class="state-panel state-error" role="alert">
      <div><strong>Não foi possível carregar os planos.</strong><p>O catálogo pode estar temporariamente indisponível.</p></div>
      <button type="button" class="retry-button" :disabled="pending" @click="refresh">Tentar novamente</button>
    </div>
    <div v-else-if="!plans?.length" class="state-panel" role="status">
      <div><strong>Nenhum plano disponível.</strong><p>Não há opções comerciais publicadas no momento.</p></div>
    </div>
    <section v-else class="plans-grid" aria-label="Planos disponíveis">
      <article v-for="plan in plans" :key="plan.code" class="plan-card" :class="{ featured: plan.is_default }">
        <div class="plan-topline">
          <span v-if="plan.is_default" class="recommended">Recomendado</span>
          <span v-else class="plan-code">{{ plan.code }}</span>
        </div>
        <h2>{{ plan.name }}</h2>
        <p class="plan-description">{{ plan.description || 'Uma configuração para começar com clareza.' }}</p>
        <div class="price"><span>R$</span> {{ formatPrice(plan.monthly_price) }} <small>/mês</small></div>
        <p class="trial">{{ plan.trial_days ? `${plan.trial_days} dias para testar` : 'Sem período de teste informado' }}</p>

        <div class="modules-heading"><span>Inclui</span><span>{{ plan.modules.length }} módulos</span></div>
        <ul class="module-list">
          <li v-for="module in plan.modules" :key="module.code" class="module-item">
            <div class="module-title"><span class="check">✓</span><strong>{{ module.name }}</strong><span class="module-badge" :class="{ plus: !module.is_base && !module.is_free }">{{ moduleLabel(module) }}</span></div>
            <p v-if="module.description">{{ module.description }}</p>
            <div class="module-meta"><span>{{ modulePrice(module) }}</span><span v-if="dependencyNames(module)">Depende de: {{ dependencyNames(module) }}</span></div>
            <div v-if="Object.keys(module.limits).length" class="limits">
              <span v-for="(value, key) in module.limits" :key="key"><b>{{ formatLimit(value) }}</b> {{ formatLimitKey(String(key)) }}</span>
            </div>
          </li>
        </ul>
      </article>
    </section>

    <p class="footnote">Preços mensais exibidos conforme o catálogo público. Para contratar ou esclarecer dúvidas, fale com nossa equipe. Nenhum pagamento é processado nesta página.</p>
  </main>
</template>

<style scoped>
.plans-shell { min-height: 100vh; padding: 28px clamp(20px, 5vw, 72px) 56px; background: #f7f5ef; color: #17201d; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
.plans-header, .intro, .foundation, .plans-grid, .footnote { width: min(1160px, 100%); margin-inline: auto; }
.plans-header { display: flex; justify-content: space-between; align-items: center; }
.brand { color: #17201d; font-size: 1.1rem; font-weight: 950; letter-spacing: -.04em; text-decoration: none; }
.back-link { color: #52605a; font-size: .9rem; font-weight: 750; text-decoration: none; }
.intro { padding: clamp(64px, 10vw, 120px) 0 48px; }
.eyebrow { margin: 0 0 12px; color: #177b67; font-size: .72rem; font-weight: 900; letter-spacing: .15em; text-transform: uppercase; }
h1, h2, p { margin-top: 0; } h1 { max-width: 760px; margin-bottom: 20px; font-size: clamp(2.8rem, 7vw, 6.4rem); line-height: .93; letter-spacing: -.075em; } h2 { letter-spacing: -.045em; }
.intro-copy { max-width: 640px; margin-bottom: 0; color: #64716b; font-size: 1.08rem; line-height: 1.65; }
.foundation { display: grid; grid-template-columns: 64px 1fr; gap: 22px; max-width: 820px; margin-bottom: 48px; padding: 24px; border: 1px solid #cfe2d9; border-radius: 18px; background: #eaf4ee; }
.foundation-mark { color: #177b67; font-size: .8rem; font-weight: 900; } .foundation h2 { margin-bottom: 9px; font-size: 1.35rem; } .foundation p:last-child { max-width: 700px; margin-bottom: 0; color: #52605a; line-height: 1.55; }
.state-panel { display: flex; justify-content: center; align-items: center; gap: 16px; width: min(600px, 100%); min-height: 150px; margin: 0 auto 32px; padding: 28px; border: 1px solid #deded5; border-radius: 18px; background: #fff; } .state-panel p { margin: 6px 0 0; color: #718078; } .state-error { border-color: #f2c9bd; } .retry-button { margin-left: 12px; padding: 10px 14px; border: 0; border-radius: 8px; background: #17201d; color: white; font-weight: 800; cursor: pointer; } .retry-button:disabled { opacity: .55; cursor: wait; } .loader { width: 22px; height: 22px; border: 3px solid #cfe2d9; border-top-color: #177b67; border-radius: 50%; animation: spin .8s linear infinite; } @keyframes spin { to { transform: rotate(360deg); } }
.plans-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(290px, 1fr)); align-items: start; gap: 18px; }
.plan-card { padding: 26px; border: 1px solid #deded5; border-radius: 18px; background: #fff; box-shadow: 0 12px 30px rgba(23,32,29,.05); } .plan-card.featured { border: 2px solid #177b67; box-shadow: 0 18px 44px rgba(23,123,103,.13); } .plan-topline { min-height: 22px; } .recommended, .plan-code { color: #177b67; font-size: .7rem; font-weight: 900; letter-spacing: .1em; text-transform: uppercase; } .plan-card h2 { margin: 16px 0 8px; font-size: 1.7rem; } .plan-description { min-height: 48px; color: #718078; line-height: 1.5; }
.price { margin-top: 24px; font-size: 2.45rem; font-weight: 950; letter-spacing: -.07em; } .price span, .price small { font-size: .9rem; letter-spacing: 0; } .price small { color: #718078; font-weight: 650; } .trial { margin: 5px 0 26px; color: #177b67; font-size: .85rem; font-weight: 800; }
.modules-heading { display: flex; justify-content: space-between; padding: 14px 0 10px; border-top: 1px solid #e8e8e0; color: #718078; font-size: .76rem; font-weight: 850; text-transform: uppercase; letter-spacing: .08em; } .module-list { display: grid; gap: 12px; margin: 0; padding: 0; list-style: none; } .module-item { padding: 12px 0; border-bottom: 1px solid #edf0ec; } .module-title { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; } .check { color: #177b67; font-weight: 950; } .module-title strong { font-size: .95rem; } .module-badge { margin-left: auto; padding: 4px 7px; border-radius: 5px; background: #eaf4ee; color: #177b67; font-size: .64rem; font-weight: 900; text-transform: uppercase; } .module-badge.plus { background: #fff0cf; color: #95630d; } .module-item p { margin: 7px 0; color: #718078; font-size: .82rem; line-height: 1.45; } .module-meta { display: flex; justify-content: space-between; gap: 8px; color: #718078; font-size: .73rem; } .limits { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; } .limits span { padding: 4px 6px; border-radius: 5px; background: #f2f3ef; color: #718078; font-size: .7rem; } .limits b { color: #17201d; }
.footnote { margin-top: 28px; color: #718078; font-size: .8rem; text-align: center; }
@media (max-width: 600px) { .foundation { grid-template-columns: 1fr; gap: 10px; } .state-panel { align-items: flex-start; flex-direction: column; } .retry-button { margin: 0; } .plan-card { padding: 22px; } }
</style>
