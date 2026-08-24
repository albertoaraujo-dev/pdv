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

## Observações

- Scripts de `backup-db.sh` e `restore-db.sh` executam backup custom do PostgreSQL e restore protegido por confirmação.
- `backend/config/settings/production.py` ainda é base mínima; produção real exigirá configuração de proxy, HTTPS, secrets, HSTS e backup.
- Estoque transacional ainda não foi implementado.
- Pix automatizado, cartão integrado, TEF/maquininha, impressão física e dispositivos ainda não foram implementados.
- O cartão externo e o Pix manual existentes são apenas registros operacionais, sem autorização, webhook ou conciliação automática.
- Deploy automático para a VPS está configurado via GitHub Actions, com backup antes de cada deploy, rollback manual por commit/tag e healthcheck público.

## Estrutura

- `backend/`: Django e API
- `frontend/`: Nuxt 4
- `deploy/`: arquivos futuros de deploy
- `docs/`: documentacao tecnica
- `infra/`: infraestrutura local/futura
- `scripts/`: scripts operacionais
# AbacatePay sandbox

Configure `ABACATEPAY_API_KEY` only in the backend/container environment. The optional `ABACATEPAY_API_BASE_URL` defaults to `https://api.abacatepay.com/v2`; use the sandbox base URL/key supplied by AbacatePay when applicable. Never use an `NUXT_PUBLIC_*` variable for the key.

After a sale exists, the authenticated tenant-scoped endpoints are:

- `POST /api/sales/sales/{id}/abacatepay/` creates or returns the idempotent transparent PIX.
- `GET /api/sales/sales/{id}/abacatepay/` refreshes its provider status.
- `POST /api/sales/sales/{id}/abacatepay/simulate/` calls the provider sandbox simulation endpoint.

These endpoints return `id`, `status`, `brCode`, and `brCodeBase64`. They do not change `Sale.status` or inventory; the existing `pix_manual` flow remains unchanged.
