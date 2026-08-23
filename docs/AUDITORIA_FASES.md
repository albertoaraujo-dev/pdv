# Auditoria de Fechamento das Fases

## Estado atual

Esta auditoria separa funcionalidade implementada de fase formalmente fechada.
Uma fase so deve ser marcada como encerrada depois de validacao automatica,

| Fase | Estado | Pendencia principal |
| --- | --- | --- |
| 1 | Fechada no escopo local | Revalidar persistencia apenas se o ambiente mudar. |
| 2 | Parcial | Consolidar evidencia de isolamento por organizacao/loja. |
| 3 | Parcial | Reset de senha seguro implementado; falta teste manual e SMTP real. |
| 4 | Fechada no escopo da API base | APIs sao deliberadamente de leitura; escritas ficam no Admin/PDV. Falta teste manual final. |
| 5 | Parcial | Executar e registrar os testes manuais restantes do Admin. |
| 6 | Parcial | Registrar os fluxos posteriores ao Pedaço 25 e validar comprovante/PDV no dominio. |
| 6A | Parcial | Praticar rollback real, reinicio com persistencia e validar cookies/SMTP na VPS. |
| 7 | Parcial | Registrar aprovacao manual de entrada, baixa, saldo insuficiente e estorno idempotente. |

## Fase 3

Implementado o reset de senha fora do Admin:

- pedido com resposta genérica para não revelar existência de usuário;
- token padrão do Django, de uso único;
- validação de senha e confirmação;
- limpeza de `must_change_password` após redefinição;
- envio por backend de e-mail configurável.

Pendências para fechamento:

- configurar SMTP real na VPS;
- solicitar redefinição para usuário existente e inexistente;
- usar o link recebido e confirmar login com a nova senha;
- confirmar que o token não pode ser reutilizado.

## Fase 4

O escopo da API base é leitura. O Admin é o canal de escrita gerencial e o PDV
é o canal de escrita operacional. Não criar endpoints genéricos de escrita
apenas para satisfazer o roadmap, pois isso duplicaria regras e aumentaria o
risco de violação de tenant.

## Fase 6A

Já existem deploy automático, backup de banco e mídia, restore protegido,
monitoramento público, usuário `deployer`, HTTPS e firewall. Ainda é necessário
executar uma vez o checklist operacional completo e registrar o resultado:

1. Login no Admin pelo domínio.
2. Login no PDV pelo domínio.
3. Venda e cancelamento pelo domínio.
4. Reinício dos containers sem perda de dados.
5. Deploy de um commit anterior e retorno ao commit atual.
6. Restore em banco temporário, já validado nesta VPS.

## Fase 7

O código implementa baixa transacional, saldo por loja, entrada manual auditada,
saldo insuficiente e estorno idempotente. O fechamento depende de aprovação
manual dos quatro cenários operacionais e da atualização do guia da fase.
