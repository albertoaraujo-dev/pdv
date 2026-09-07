# FASE 9B - GESTAO DE CAIXA

## Objetivo

Adicionar o nucleo operacional de caixa por loja, sem ainda tornar a abertura
obrigatoria para criar vendas existentes.

## Escopo implementado

- Sessao de caixa tenant-scoped por organizacao e loja.
- Apenas uma sessao aberta por loja.
- Valor de abertura e valor contado no fechamento.
- Suprimento e sangria com valor positivo e motivo obrigatorio.
- Resumo de suprimentos, sangrias e dinheiro esperado.
- Fechamento idempotente e preservacao do historico.
- Endpoints protegidos pela mesma politica do modulo de vendas.
- Registros somente leitura no Admin.

## Endpoints

- `GET /api/sales/cash-register/`
- `POST /api/sales/cash-register/`
- `GET /api/sales/cash-register/{id}/`
- `POST /api/sales/cash-register/{id}/movements/`
- `POST /api/sales/cash-register/{id}/close/`

## Validacoes automaticas realizadas

- `python manage.py check`: OK.
- `python manage.py makemigrations --check --dry-run`: OK.
- Suite `apps.sales`: 34 testes passando.

## Teste manual pendente

1. Autenticar no dominio com um usuario de caixa autorizado.
2. Abrir uma sessao para uma loja com valor inicial.
3. Consultar a sessao e confirmar o dinheiro esperado.
4. Registrar um suprimento e confirmar o novo total.
5. Registrar uma sangria e confirmar o novo total.
6. Fechar o caixa informando o valor contado.
7. Confirmar que uma segunda abertura para a mesma loja e rejeitada.
8. Confirmar que usuario sem acesso a loja nao consegue consultar a sessao.

Nao commitar esta fase antes da aprovacao manual dos endpoints e regras de
abertura, movimentacao e fechamento.
