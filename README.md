# PDV Final

Base para ERP + PDV com Django, Django REST Framework, Nuxt 4, PostgreSQL e Redis.

## Requisitos

- Docker
- Docker Compose

## Subir o projeto

```bash
docker compose up --build
```

Para subir em segundo plano:

```bash
docker compose up -d --build
```

URLs locais:

- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- Healthcheck backend: http://localhost:8000/health/
- Django Admin: http://localhost:8000/admin/

## Parar o projeto

```bash
docker compose down
```

## Validações

Backend:

```bash
docker compose exec backend python manage.py check
docker compose exec backend python manage.py makemigrations --check --dry-run
docker compose exec backend python manage.py test apps.accounts apps.tenants apps.catalog
```

Frontend:

```bash
docker compose exec frontend npm run build
```

Depois de rodar `npm run build` dentro do container frontend de desenvolvimento, reinicie o serviço para voltar ao estado dev:

```bash
docker compose restart frontend
```

## Estado Atual

- Stack local com Docker Compose, PostgreSQL, Redis, Django e Nuxt.
- Modelo multi-tenant inicial com organizações, lojas, perfis, acessos por loja, categorias, unidades e produtos.
- Autenticação web por sessão e CSRF.
- Sessões independentes para API/PDV e Django Admin no mesmo navegador.
- Login/logout, `/api/auth/me/` e troca de senha autenticada.
- PDV mostra o usuário logado e permite sair sem encerrar a sessão do Django Admin.
- Auditoria e lockout de tentativas de login.
- Bloqueios para usuário, perfil e organização inativos.
- Troca obrigatória de senha inicial para usuários criados por gerente.
- Hardening local de cookies, CSRF, sessão, headers e IP auditado.
- Fase 3 de autenticação, autorização e segurança concluída e validada.
- Fase 4 iniciada com API DRF de leitura do catálogo em `/api/catalog/`.
- API DRF administrativa de leitura de usuários disponível em `/api/tenants/users/`.
- API DRF administrativa de leitura de organizações e lojas disponível em `/api/tenants/organizations/` e `/api/tenants/stores/`.
- Schema OpenAPI inicial disponível em `/api/schema/`.
- Página inicial de documentação da API disponível em `/api/docs/`.
- Fase 4 de API base com DRF concluída e validada.
- Fase 5 de painel administrativo em evolução contínua, com escopo por organização/loja e gestão de acessos.
- Fase 6 de PDV operacional em andamento, com vendas persistidas, pagamentos manuais, troco, idempotência e resumo da venda.
- Fundação da Fase 9A de billing SaaS: planos, assinaturas, faturas, pagamentos manuais e eventos de provedor são separados do domínio de vendas.
- Billing modular no MVP: catálogo de módulos ativos, módulos incluídos por plano, limites JSON e add-ons/overrides por assinatura.
- A disponibilidade é decidida no backend: somente assinaturas `trial` não expiradas ou `active` liberam módulos; `past_due`, `suspended` e `cancelled` não liberam.
- Novas organizações criadas pelo Admin global recebem uma assinatura trial idempotente do plano padrão ativo (`mvp` na instalação inicial), sem gateway ou cobrança; o plano inclui `sales`, enquanto `core` e `catalog` são base obrigatória.
- Organizações legadas podem ser regularizadas sem cobrança com `python manage.py provision_subscriptions`; o comando também pode receber `--organization ID` e nunca altera assinaturas existentes.
- O ciclo de cobrança é `trial`, `active`, `past_due`, `suspended` e `cancelled`; faturas vencidas entram em carência configurável (`BILLING_GRACE_PERIOD_DAYS`, padrão 7) e a rotina idempotente `python manage.py billing_suspension_routine` suspende após a carência (`--dry-run` disponível).
- Cancelamento e mudanças de plano são serviços restritos ao administrador global. Cada mudança é registrada em `SubscriptionChange`; faturas e módulos históricos nunca são apagados, e um pagamento reativa assinaturas não canceladas.
- A geração mensal idempotente cria faturas abertas por período, sem gateway ou cobrança automática: `python manage.py generate_subscription_invoices --period 2026-09`; aceita `--organization ID` e `--dry-run`. Uma fatura por assinatura e período é garantida no banco, e o preço do plano vigente é congelado na fatura.
- Usuários autenticados de uma organização podem consultar seu status somente leitura em `/api/billing/status/`, incluindo ciclo da assinatura, plano, módulos efetivos com limites e as dez notificações mais recentes. O endpoint é escopado à organização do usuário e não expõe payloads de provedor; superusuários usam o Admin global para billing.
- O catálogo comercial somente leitura está disponível publicamente em `GET /api/billing/plans/`, com planos ativos, preço mensal, trial, módulos incluídos, limites, dependências e preços mensais. Apenas módulos ativos são retornados; `core` e `catalog` aparecem como base/gratuitos, enquanto `sales` e módulos PLUS aparecem com sua semântica comercial. Não há endpoints de mutação no catálogo.
- O MVP de ativação sem gateway permite a administradores e gerentes solicitar um plano ou add-on PLUS em `POST /api/billing/requests/` e consultar o histórico em `GET /api/billing/requests/`. A chave `request_key` (ou o header `Idempotency-Key`) torna solicitações abertas idempotentes. Somente o administrador global pode aprovar ou rejeitar pelo Django Admin; a aprovação altera a assinatura por serviços existentes, sem marcar faturas como pagas ou ignorar cobrança.

## Observações

- Scripts de `backup-db.sh` e `restore-db.sh` executam backup custom do PostgreSQL e restore protegido por confirmação.
- `backend/config/settings/production.py` ainda é base mínima; produção real exigirá configuração de proxy, HTTPS, secrets, HSTS e backup.
- O estoque disponível considera reservas de pagamentos pendentes; reservas são liberadas ao cancelar e convertidas em baixa ao confirmar o pagamento.
- Pix automatizado via AbacatePay está disponível em sandbox; cartão integrado, TEF/maquininha, impressão física e dispositivos ainda não foram implementados.
- O cartão externo continua sem integração TEF/POS: a venda cria um registro interno aprovado, consultável em `/api/sales/sales/{id}/transaction/`, e gerente/admin pode conciliá-lo manualmente em `/api/sales/sales/{id}/transaction/reconcile/`; nenhuma dessas ações altera venda ou estoque.
- Deploy automático para a VPS ocorre via GitHub Actions somente após o workflow `CI` concluir com sucesso para `main`, com backup antes de cada deploy e healthcheck público. O workflow `Deploy VPS` também pode ser executado manualmente com `deploy_ref` (commit ou tag) para rollback.

## Estrutura

- `backend/`: Django e API
- `frontend/`: Nuxt 4
- `deploy/`: arquivos futuros de deploy
- `docs/`: documentacao tecnica
- `infra/`: infraestrutura local/futura
- `scripts/`: scripts operacionais
# AbacatePay sandbox

Configure `ABACATEPAY_API_KEY` only in the backend/container environment. The optional `ABACATEPAY_API_BASE_URL` defaults to `https://api.abacatepay.com/v2`; use the sandbox base URL/key supplied by AbacatePay when applicable. Never use an `NUXT_PUBLIC_*` variable for the key.

For a sale using `pix_abacatepay`, the authenticated tenant-scoped endpoints are:

- `POST /api/sales/sales/{id}/abacatepay/` creates or returns the idempotent transparent PIX.
- `GET /api/sales/sales/{id}/abacatepay/` refreshes its provider status.
- `POST /api/sales/sales/{id}/abacatepay/simulate/` calls the provider sandbox simulation endpoint.
- `POST /webhooks/abacatepay/?webhookSecret=...` validates the HMAC signature and reconciles `transparent.completed` events.

Creating the sale reserves stock and leaves it as `pending_payment`. A paid provider status atomically converts the reservation to the definitive sale deduction and marks the sale `completed`; cancellation releases the reservation idempotently. The existing `pix_manual` and cash flows remain unchanged.

Configure `ABACATEPAY_WEBHOOK_SECRET` with the same secret registered in the
AbacatePay webhook. Register the public endpoint over HTTPS and subscribe to
`transparent.completed`.

For sandbox testing only, set `ABACATEPAY_ALLOW_SIMULATION=True`. Keep it
disabled in production with real payment credentials.

## Billing SaaS (Fase 9A)

Billing é separado de `SalePayment`, `CardPaymentTransaction` e seus webhooks. No MVP, o
administrador global registra pagamentos manuais pela ação da fatura no Django Admin;
isso marca a fatura como paga e a assinatura como ativa. Organizações podem operar sem
gateway configurado. Operadores e administradores de uma organização não podem alterar
billing. Dados históricos permanecem preservados quando uma assinatura é suspensa.
Avisos de vencimento, inadimplência e suspensão são registrados de forma idempotente em `BillingNotification`; a entrega permanece abstrata, sem gateway ou provedor de e-mail nesta etapa. Configure `BILLING_DUE_SOON_DAYS` e `BILLING_SUSPENSION_WARNING_DAYS` para os prazos dos avisos.
Use `python manage.py generate_billing_notifications --dry-run` para simular a rotina.

Módulos são administrados no Django Admin, sempre restrito ao superusuário global. Gerentes podem adicionar ou remover add-ons somente pelo serviço backend, com validação de organização, período e limites; o frontend não é uma camada de autorização.

As rotinas de billing são executadas diariamente pelo workflow `Billing Routine`. Elas geram faturas e registros de aviso, marcam inadimplência e suspendem assinaturas após a carência. O workflow não cobra automaticamente nem chama gateway; `workflow_dispatch` permite execução manual.

Modelo comercial de módulos:

- `core` é obrigatório e gratuito para toda organização.
- `catalog` acompanha o `core` e não é vendido isoladamente, pois é necessário para um produto utilizável.
- `sales` (PDV) é o primeiro módulo vendável e depende de `catalog`.
- `inventory`, `cash`, `reports`, `customers`, `finance`, `delivery` e outros são módulos PLUS, vendidos no plano ou como add-ons.
- Dependências, módulos ativos e limites devem ser validados no backend; dados históricos não são apagados quando um módulo é removido.
- `core` e `catalog` são módulos base obrigatórios e efetivos em toda assinatura `trial` ou `active`; eles não precisam ser incluídos no plano nem podem ser removidos como add-on.
- O plano usado na criação é escolhido por `Plan.is_default=True` e `is_active=True`, não por gateway; deve incluir o módulo `sales`.
- A UI pode consultar `GET /api/billing/plans/` sem sessão para montar a oferta comercial; a resposta não contém organizações, assinaturas, faturas ou dados de provedor.
- Dependências são registros protegidos em `ModuleDependency`. Um módulo com dependência indisponível não é efetivo, e ciclos são rejeitados na validação.
- O catálogo inicial de módulos é administrado pelo superusuário no Django Admin; instalações existentes preservam seus registros e podem marcar `core`/`catalog` como módulos base.
- Há drift conhecido nas migrações de `accounts` em instalações antigas; confirme o estado aplicado antes de promover novas migrações e não remova dados históricos.

Faturas novas preservam o plano e cada add-on PLUS como itens com preço congelado. `core` e `catalog` nunca são cobrados; preços podem ser ajustados antes do pagamento por administrador global. Faturas antigas continuam usando o campo `amount` e não são reconstituídas sem dados históricos suficientes.
