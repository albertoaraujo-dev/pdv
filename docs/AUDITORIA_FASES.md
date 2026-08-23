# Auditoria de Fechamento das Fases

## Estado atual

Esta auditoria separa funcionalidade implementada de fase formalmente fechada.
Uma fase so deve ser marcada como encerrada depois de validacao automatica e manual.

| Fase | Estado | Pendencia principal |
| --- | --- | --- |
| 1 | Fechada | Infraestrutura local validada. |
| 2 | Fechada no escopo atual | Isolamento por organizacao/loja validado. |
| 3 | Fechada no escopo atual | Reset de senha validado; SMTP externo fica como configuracao operacional futura. |
| 4 | Fechada no escopo da API base | APIs sao deliberadamente de leitura; escritas ficam no Admin/PDV. |
| 5 | Fechada no escopo atual | Admin, Unfold, filtros, escopo e formularios validados manualmente. |
| 6 | Fechada no escopo atual | PDV, venda, pagamentos manuais, comprovante e cancelamento validados. |
| 6A | Fechada como staging operacional | Deploy, HTTPS, backups, restore, monitoramento, reinicio e rollback validados. |
| 7 | Fechada no escopo atual | Baixa, entrada, saldo insuficiente, estorno idempotente e consulta validados. |

## Fase 3

Implementado o reset de senha fora do Admin:

- pedido com resposta genérica para não revelar existência de usuário;
- token padrão do Django, de uso único;
- validação de senha e confirmação;
- limpeza de `must_change_password` após redefinição;
- envio por backend de e-mail configurável.

Configuracao futura, fora do fechamento funcional:

- configurar SMTP real na VPS para envio externo.

## Fase 4

O escopo da API base é leitura. O Admin é o canal de escrita gerencial e o PDV
é o canal de escrita operacional. Não criar endpoints genéricos de escrita
apenas para satisfazer o roadmap, pois isso duplicaria regras e aumentaria o
risco de violação de tenant.

## Fase 6A

Já existem deploy automático, backup de banco e mídia, restore protegido,
monitoramento público, usuário `deployer`, HTTPS e firewall. O checklist
operacional completo foi executado e aprovado:

1. Login no Admin pelo domínio.
2. Login no PDV pelo domínio.
3. Venda e cancelamento pelo domínio.
4. Reinício dos containers sem perda de dados.
5. Deploy de um commit anterior e retorno ao commit atual.
6. Restore em banco temporário, já validado nesta VPS.

## Fase 7

O código implementa baixa transacional, saldo por loja, entrada manual auditada,
saldo insuficiente e estorno idempotente. Os quatro cenários operacionais foram
aprovados manualmente.
