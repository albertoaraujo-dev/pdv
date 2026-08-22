# Deploy Automatico na VPS

O workflow `.github/workflows/deploy-vps.yml` faz deploy a cada push na branch
`main`. Tambem pode ser executado manualmente pela opcao **Run workflow** no
GitHub Actions.

## Secrets

Configure estes secrets no ambiente `production` do repositorio:

- `VPS_HOST`: `187.127.59.172`
- `VPS_USER`: usuario SSH, normalmente `root` nesta VPS
- `VPS_APP_DIR`: `/opt/pdv`
- `VPS_SSH_KEY_B64`: chave privada SSH exclusiva para o GitHub Actions,
  codificada em Base64 e sem passphrase
- `VPS_KNOWN_HOSTS`: saida de `ssh-keyscan -H 187.127.59.172`

Nao use a chave pessoal de desenvolvimento. Crie uma chave exclusiva para o
deploy e instale a chave publica em `/root/.ssh/authorized_keys` da VPS.

## Pre-requisitos da VPS

- O repositorio deve estar clonado em `/opt/pdv`.
- O remote `origin` deve apontar para o repositorio correto.
- `/opt/pdv/deploy/.env.staging` deve existir somente na VPS.
- O usuario SSH deve conseguir executar Docker sem prompt interativo.

O deploy atualiza o clone para o commit exato que disparou o workflow, constroi
backend, migration e frontend, cria um backup PostgreSQL com retencao de 14 dias,
executa `migrate` e `collectstatic`, recria os servicos e valida
`https://ligara.online/health/`.

## Backup e restore

Os backups ficam em `/opt/pdv/backups`, fora do Git, com permissao restrita.
Execute manualmente na VPS para criar um backup:

```bash
cd /opt/pdv
./scripts/backup-db.sh
```

Para restaurar, informe explicitamente a confirmacao destrutiva:

```bash
cd /opt/pdv
CONFIRM_RESTORE=YES ./scripts/restore-db.sh /opt/pdv/backups/pdv-YYYYmmddTHHMMSSZ.dump
```

O restore para backend, frontend e proxy durante a operacao e os inicia
novamente ao final. Valide o healthcheck e o login depois do restore.

## Rollback

O workflow manual aceita um commit ou tag no campo `deploy_ref`. Para
voltar o codigo, abra **Actions > Deploy VPS > Run workflow** e informe o commit
anterior. O deploy cria um backup antes de executar migrations.

Restore de banco e rollback de codigo sao operacoes separadas. Se o release
anterior exigir um schema antigo, restaure primeiro um backup compativel e so
depois execute o rollback do codigo.

## Primeira configuracao

Na VPS, valide o clone antes de ativar o workflow:

```bash
cd /opt/pdv
git remote -v
git status
test -f deploy/.env.staging
```

Para gerar e cadastrar a chave em Base64 no PowerShell:

```powershell
$keyB64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes("$env:TEMP\pdv-actions_ed25519"))
gh secret set VPS_SSH_KEY_B64 --env production --body $keyB64
```

Depois de configurar os secrets, use **Run workflow** para o primeiro deploy.
