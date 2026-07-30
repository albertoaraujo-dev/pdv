# PDV Final

Base inicial para ERP + PDV com Django, Django REST Framework, Nuxt 3, PostgreSQL e Redis.

## Requisitos

- Docker
- Docker Compose

## Subir o projeto

```bash
docker compose up --build
```

URLs locais:

- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- Healthcheck backend: http://localhost:8000/health/

## Parar o projeto

```bash
docker compose down
```

## Estrutura

- `backend/`: Django e API
- `frontend/`: Nuxt 3
- `deploy/`: arquivos futuros de deploy
- `docs/`: documentacao tecnica
- `infra/`: infraestrutura local/futura
- `scripts/`: scripts operacionais
