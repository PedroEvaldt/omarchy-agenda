# Conectar o Google Calendar

Passo a passo para a aba Agenda mostrar os eventos da sua conta Google. Leva uns quinze minutos na primeira vez, quase tudo no site do Google Cloud.

## Por que isso é necessário

O Google não deixa um programa ler o seu calendário só com a sua senha. O caminho é o OAuth 2.0: você cria um "app" no Google Cloud, que é só uma identidade para o plugin; o plugin pede acesso; você aprova numa tela do Google; o Google devolve um token. O plugin guarda esse token e o renova sozinho. A sua senha nunca passa por aqui.

Como o app é seu, criado na sua conta, nenhum terceiro vê seus dados.

## 1. Criar o projeto e ligar a API

1. Abra https://console.cloud.google.com e entre com a conta do calendário.
2. No topo, crie um projeto novo. Nome sugerido: `omarchy-agenda`.
3. Com o projeto selecionado, vá em **APIs e serviços › Biblioteca**, procure **Google Calendar API** e clique em **Ativar**.

## 2. Tela de consentimento

1. **APIs e serviços › Tela de permissão OAuth** (pode aparecer como "Google Auth Platform › Branding").
2. Tipo de usuário **Externo**. Preencha nome do app, e-mail de suporte e e-mail do desenvolvedor. O resto pode ficar vazio.
3. Em **Público** (ou "Usuários de teste"), adicione o seu próprio e-mail.

Importante: enquanto o app está em **Teste**, o Google invalida o refresh token a cada sete dias e você teria de autorizar de novo toda semana. Para evitar isso, na mesma tela clique em **Publicar o app**. Ele passa para "Em produção" sem precisar de verificação; na tela de autorização vai aparecer um aviso de "app não verificado", e você clica em **Avançado › Acessar**. É normal para apps de uso pessoal.

## 3. Credenciais do tipo "App para computador"

1. **APIs e serviços › Credenciais › Criar credenciais › ID do cliente OAuth**.
2. Tipo de aplicativo: **App para computador**. Nome: `omarchy-agenda`.
3. Clique em **Fazer o download do JSON**. O arquivo se chama algo como `client_secret_1234-abcd.apps.googleusercontent.com.json`.

Esse JSON identifica o seu app. Não vai para o repositório: o `.gitignore` já o exclui, e o próximo passo copia ele para `~/.config/agenda/` com permissão só sua.

## 4. Autorizar

```bash
agenda google setup ~/Downloads/client_secret_*.json
```

O comando copia o JSON, cria o `~/.config/agenda/config.toml`, abre o navegador na tela do Google e espera você aprovar. Ao voltar, guarda o token no keyring do sistema, ou num arquivo `token.json` só seu se não houver keyring, e faz a primeira sincronização. A aba Agenda do painel atualiza na hora.

Para ver como ficou:

```bash
agenda google status
```

## 5. Escolher calendários

Por padrão só o calendário principal entra. Para ver os outros:

```bash
agenda google calendars
```

Copie os ids desejados para `~/.config/agenda/config.toml`:

```toml
[google]
calendars = ["primary", "familia@group.calendar.google.com"]
write_calendar = "primary"
```

## 6. Ligar o serviço

Sem ele, a sincronização só acontece quando você aperta `r` no painel ou roda `agenda sync`. O serviço sincroniza a cada cinco minutos e manda os lembretes:

```bash
agenda service install
```

Ele vira um serviço `systemd --user` chamado `agendad`, que sobe junto com a sessão. Para acompanhar:

```bash
journalctl --user -u agendad -f
```

Lembretes e resumo da manhã se configuram no mesmo `config.toml`:

```toml
[reminders]
minutes_before = 10
morning_summary = "08:00"
```

## Desfazer tudo

```bash
agenda service uninstall
agenda google logout
```

E revogue o acesso em https://myaccount.google.com/permissions, onde o app aparece com o nome que você deu.

## Problemas comuns

- **"redirect_uri_mismatch"**: o cliente OAuth não é do tipo "App para computador". Crie outro com o tipo certo e rode o `setup` de novo.
- **"access_denied" ou "app bloqueado"**: seu e-mail não está em usuários de teste, ou o app não foi publicado. Volte ao passo 2.
- **Pede autorização toda semana**: app ainda em "Teste". Publique, passo 2.
- **Painel mostra "erro de sync"**: passe o mouse sobre o texto no rodapé para ver a mensagem, ou rode `agenda sync` no terminal.
