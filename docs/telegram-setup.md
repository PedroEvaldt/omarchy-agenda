# Conectar o Telegram

Com isso você manda uma mensagem do celular e ela vira tarefa ou evento na barra. Leva cinco minutos. Não precisa de servidor nem de URL pública: o próprio `agendad` pergunta ao Telegram se chegou algo.

## 1. Criar o bot

1. No Telegram, abra uma conversa com **@BotFather**.
2. Mande `/newbot`. Ele pede um nome de exibição, por exemplo `Agenda`, e depois um nome de usuário terminado em `bot`, por exemplo `pedro_agenda_bot`.
3. Ele responde com o **token**, uma linha parecida com `123456789:AAH...`. Esse token é a senha do bot: não vai para o repositório nem para prints.

## 2. Parear

```bash
agenda telegram setup 123456789:AAH...
```

O comando fica esperando. Abra o bot no Telegram, pelo nome de usuário que você escolheu, e mande qualquer mensagem. O plugin guarda o id da sua conversa em `~/.config/agenda/telegram.json`, com permissão só sua, e responde "Pareado". Dali em diante só esse chat é atendido; qualquer outra pessoa que encontrar o bot não recebe nada.

Depois, reinicie o serviço para ele passar a atender:

```bash
agenda service restart
```

Sem o serviço ligado, o bot não responde. `agenda service status` diz se ele está `active`.

## 3. Usar

Mande o que quer lembrar. Sem hora vira tarefa, com hora vira evento no seu Google Calendar:

| Você manda | O que acontece |
|---|---|
| `pagar luz amanhã` | tarefa, prazo amanhã |
| `dentista qui 15h` | evento quinta das 15h às 16h |
| `t: reunião 15h` | tarefa, mesmo tendo hora |
| `e: viagem dia 20` | evento de dia todo |
| `relatório sex !` | tarefa com prioridade |

Toda criação volta com um botão **Desfazer**. Comandos curtos, usando o id de quatro letras que o bot mostra:

| Você manda | O que acontece |
|---|---|
| `feito 7k2a` | conclui, com botão Reabrir |
| `adiar 7k2a` ou `adiar 7k2a 3` | empurra o prazo |
| `sub 7k2a ligar antes` | subpasso |
| `apagar 7k2a` | lixeira, com botão Restaurar |
| `lista` | tarefas abertas por seção |
| `hoje` | eventos e tarefas de hoje |
| `agenda` | os próximos sete dias |
| `ajuda` | este resumo |

Para testar frases sem mandar nada pelo Telegram, no terminal:

```bash
agenda bridge "dentista qui 15h"
```

## Trocar de canal no futuro

Toda a conversa está em `lib/agenda_bridge.py`, que não sabe o que é Telegram. O arquivo `lib/agenda_telegram.py` só traduz mensagens e cliques de botão de lá para cá. Para WhatsApp, Signal ou Matrix, escreve-se outro tradutor do mesmo tamanho e a gramática continua igual.

## Desfazer

```bash
agenda telegram logout
```

E, no BotFather, `/deletebot` ou `/revoke` para invalidar o token.
