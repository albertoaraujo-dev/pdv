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
backend, migration e frontend, executa `migrate` e `collectstatic`, recria os
servicos e valida `https://ligara.online/health/`.

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
