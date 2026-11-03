# Especificação: plugin Agenda para o Omarchy 4

Documento vivo. Descreve o que o plugin faz, como é organizado e as decisões já tomadas. O que ainda está em aberto fica na última seção.

## Objetivo

Organizar duas coisas num só lugar da barra do Omarchy: **tarefas** com subpassos e **eventos** do calendário. No futuro, criar as duas por mensagem de WhatsApp, interpretada por um modelo de linguagem.

## Arquitetura

Três peças, desacopladas por um arquivo de estado e por uma CLI:

1. **Plugin do shell, em QML.** Widget na barra mais um painel quadrado de duas abas. Lê o `state.json` com `FileView` em modo watch e reage a cada mudança. Nunca escreve no arquivo: toda ação vira um comando da CLI.
2. **CLI `agenda`, em Python.** Única dona dos dados. Na fase 1 escreve direto no `state.json`; na fase 2 vira o cliente de um serviço local (`agendad`) que também sincroniza o Google Calendar.
3. **Ponte de mensagens, fase 3.** Recebe mensagens, interpreta com um modelo de linguagem, chama a mesma CLI e responde a confirmação.

Por que assim: as diretrizes do shell do Omarchy proíbem polling em widgets, porque cada widget existe uma vez por monitor e roda o dia inteiro na bateria. Toda rede fica fora do QML. E como terminal, painel, atalho e WhatsApp entram pela mesma CLI, cada fase nova não toca a interface.

```
state.json  --FileView (watch)-->  Panel  --Model.js-->  ListModels  -->  telas
telas  --Process-->  bin/agenda  --escrita atômica-->  state.json
```

## Arquivos

```
manifest.json      identidade do plugin, configurações e seção padrão na barra
BarWidget.qml      botão na barra; carrega o painel e expõe open/close/opened
Panel.qml          painel: cabeçalho, trilho das abas, rodapé, CLI e FileView
TasksView.qml      aba Tarefas
AgendaView.qml     aba Agenda
Model.js           lógica pura: seções, ordenação, rótulos, linhas dos modelos
bin/agenda         CLI em Python, só biblioteca padrão
lib/agenda_store.py    state.json: caminhos, escrita atômica, trava, notificações
lib/agenda_google.py   config.toml, OAuth 2.0, API REST do Calendar, sincronização
lib/agenda_daemon.py   agendad: laço de sync, lembretes, resumo, unidade do systemd
tests/             node --test para Model.js e contrato QML; pytest para CLI, Google e daemon
docs/google-setup.md   passo a passo da conta Google
examples/          state.json de exemplo
docs/roadmap.md    plano de estudos e fases
```

Dados em `~/.local/state/agenda/state.json`. Respeita `XDG_STATE_HOME`; a variável `AGENDA_STATE` troca o caminho, para testes. Configuração em `~/.config/agenda/`: `config.toml` sem segredos, `client_secret.json` e `token.json` com permissão 0600, todos fora do git. `AGENDA_CONFIG_DIR` troca a pasta nos testes.

Dois processos escrevem no `state.json`, a CLI e o daemon, então toda escrita pega um `flock` em `state.json.lock`, lê, altera e grava num temporário trocado com `os.replace`.

## Widget na barra

- Ícone de caixa marcada com, ao lado, o número de tarefas de hoje e atrasadas. Quando um evento com hora começa em menos de uma hora, o texto vira a hora e o título do evento.
- Tarefa atrasada pinta o ícone com a cor de urgência do tema.
- Barra vertical: só o ícone.
- Tooltip: até três itens, tarefas urgentes e eventos de hoje.

| Clique | Ação |
|---|---|
| Esquerdo | Abre e fecha o painel |
| Direito | Abre já com o foco no campo de nova tarefa |
| Meio | Recarrega o arquivo |

IPC: `omarchy-shell shell toggle pedro.agenda '{}'` abre e fecha pelo contrato open/close/opened do widget. Atalho global sugerido no README.

## Painel

**Geometria.** Quadrado de 420 unidades de `Style.space`, altura igual à largura, limitado pela tela como todo painel. O corpo rola; cabeçalho e rodapé são fixos, 40 unidades cada.

**Cabeçalho.** Seta à esquerda, nome da aba em maiúsculas no centro com dois pontinhos indicando a aba ativa, seta à direita. As duas setas trocam para a outra aba, porque são só duas. A transição desliza o trilho com `Style.duration`, que zera quando as animações do Omarchy estão desligadas.

**Aba inicial.** Tarefas, configurável em `defaultTab`.

**Rodapé.** Campo de entrada rápida à esquerda, estado da sincronização à direita ("sem sync", "sync 12:04", "erro" com tooltip). O campo muda de função conforme o contexto: nova tarefa, novo subpasso da tarefa selecionada, prazo da tarefa selecionada, ou novo evento na aba Agenda.

### Aba Tarefas

```
┌──────────────────────────────────────────┐
│  ‹            TAREFAS            ›  ● ○  │
├──────────────────────────────────────────┤
│  ATRASADAS                               │
│  ☐  Pagar conta de luz            ontem  │
│  HOJE                                    │
│  ☐  Levar exames pro dentista     15:00  │
│  ▾☐ Montar apresentação      2/4  hoje   │
│      ☑ Rascunho                          │
│      ☑ Slides                            │
│      ☐ Revisar texto                     │
│      ☐ Ensaiar                           │
│  EM BREVE                                │
│  ▸☐ Presente pra Ana          0/3  sex   │
│  SEM DATA                                │
│  ☐  Ler sobre Quickshell                 │
│  ▸ Concluídas · 3                        │
├──────────────────────────────────────────┤
│  + nova tarefa…               sync 12:04 │
└──────────────────────────────────────────┘
```

- Seções fixas nesta ordem: Atrasadas, Hoje, Em breve, Sem data, e Concluídas recolhida no fim. Dentro de cada seção: prazo mais próximo primeiro, depois hora, prioridade, criação. Sem arrastar para reordenar.
- Linha: chevron quando há subpassos, caixa, título com reticências, contador "feitos/total", prazo à direita. Prazo atrasado na cor de urgência.
- Subpassos têm um nível só. Concluir a mãe marca todos os filhos. Concluir todos os filhos não fecha a mãe: o contador fica em destaque.
- Expandir: clique na linha ou Enter. O conjunto expandido fica na memória do painel.
- Caixa: clique conclui sem selecionar. Lixeira aparece no hover.
- Excluir manda a tarefa para a lixeira e dispara uma notificação com botão Desfazer, pelo `omarchy-notification-send`.
- Concluídas e lixeira somem depois de sete dias.
- Estado vazio: "Nada por fazer."

### Aba Agenda

```
┌──────────────────────────────────────────┐
│  ‹             AGENDA            ›  ○ ●  │
├──────────────────────────────────────────┤
│  HOJE · ter 3 nov                        │
│  dia todo     Aniversário da Ana         │
│  09:00–09:30  Daily                      │
│  15:00–16:00  Dentista          Centro   │
│  AMANHÃ · qua 4 nov                      │
│  14:00–15:00  Call com cliente    󰖟     │
│  QUI 5 NOV                               │
│  nada marcado                            │
├──────────────────────────────────────────┤
│  + novo evento…               sync 12:04 │
└──────────────────────────────────────────┘
```

- Lista cronológica dos próximos sete dias, configurável em `agendaDays`. Um cabeçalho por dia; eventos de dia todo primeiro; dias vazios mostram "nada marcado".
- Linha: horário, título, local ou ícone de link à direita. Eventos que já acabaram ficam apagados. Pontinho na cor do calendário de origem, quando houver.
- Enter ou clique abre o link do evento no navegador.
- Eventos de vários dias aparecem em cada dia que cobrem, com o fim exclusivo, como no Google.
- Fase 1: eventos locais criados pela CLI. Fase 2: eventos do Google escritos pelo serviço, sem mudar nada aqui.

### Teclado

Tab e Shift+Tab são da barra: pulam para o painel vizinho. Por isso a troca de aba fica nas setas.

| Tecla | Tarefas | Agenda |
|---|---|---|
| ← → ou h l, 1 2 | Troca de aba | Troca de aba |
| ↓ ↑ ou j k | Move o cursor | Move o cursor |
| Enter | Expande ou recolhe | Abre o link |
| Espaço | Conclui ou reabre | |
| a | Novo subpasso | |
| d | Define o prazo | |
| p | Adia um dia | |
| x ou Delete | Exclui com Desfazer | |
| c | Mostra ou esconde concluídas | |
| n ou / | Foco no campo | |
| r | Recarrega | Recarrega |
| Esc | Sai do campo, senão fecha | Fecha |

Dentro do campo: Enter envia, Esc limpa ou devolve o foco à lista, Tab é engolido.

## Entrada rápida

Mesma interpretação no campo, na CLI e, no futuro, no WhatsApp. Só biblioteca padrão; sem dateparser até a fase 2.

| Pista | Efeito |
|---|---|
| hoje, amanhã, depois de amanhã | prazo relativo |
| seg … dom, segunda … domingo, com ou sem "na", "nesta", "próxima" | próxima ocorrência; o próprio dia conta como hoje |
| dia 12 | dia 12 deste mês, ou do próximo se já passou |
| 12/11, 12/11/2026 | data explícita |
| 15h, 15h30, 15:30, com ou sem "às" | hora |
| 15h-16h30 | início e fim, só para eventos |
| ! no fim | prioridade alta |

O que sobra é o título.

## Formato do state.json

```json
{
  "version": 1,
  "generatedAt": "2026-11-03T12:04:00-03:00",
  "sync": { "lastOkAt": "", "status": "none", "error": "" },
  "tasks": [
    { "id": "7k2a", "title": "Montar apresentação", "due": "2026-11-03", "dueTime": "",
      "priority": 1, "createdAt": "2026-11-01T09:00:00-03:00", "completedAt": "",
      "subtasks": [ { "id": "7k2a.1", "title": "Rascunho", "done": true } ] }
  ],
  "events": [
    { "id": "g:abc123", "calendar": "Pessoal", "calendarId": "primary", "color": "#8be9fd", "title": "Dentista", "allDay": false,
      "start": "2026-11-03T15:00:00-03:00", "end": "2026-11-03T16:00:00-03:00",
      "location": "Centro", "url": "", "description": "" }
  ],
  "trash": []
}
```

- Ids de tarefa: quatro caracteres base36 começando por letra, curtos para digitar numa mensagem. Subpassos: `<id>.<n>`.
- Prazos: `due` é "YYYY-MM-DD" no fuso local; `dueTime` é "HH:MM" ou vazio.
- Eventos com hora em ISO 8601 com fuso; eventos de dia todo só com a data e fim exclusivo. Ids `g:` vêm do Google e guardam `calendarId` para apagar depois; ids `l:` são locais.
- Escrita sempre atômica: temporário mais `os.replace`, para o painel nunca ler meio arquivo.

## CLI

```
agenda add "texto" [--due …] [--sub "x"]... [--priority]
agenda done | undo | rm | restore <id>
agenda sub add <id> "texto" | sub done | undo | rm <id.n>
agenda edit <id> [--title …] [--due …] [--no-due] [--priority 0|1]
agenda snooze <id> [dias]
agenda list [--json] [--all]
agenda event add "texto" | event rm <id> | event list
agenda parse "texto"
agenda seed
agenda path
```

## Configurações no manifest

| Chave | Tipo | Padrão | O que faz |
|---|---|---|---|
| defaultTab | enum tasks, agenda | tasks | Aba ao abrir |
| agendaDays | integer 1 a 30 | 7 | Dias na aba Agenda |
| showCompleted | boolean | false | Concluídas visíveis ao abrir |
| cliPath | path | vazio | Caminho da CLI; vazio usa a pasta do plugin |

## Fases

1. **Tarefas e eventos locais.** Este repositório. Painel, CLI, testes.
2. **Google Calendar.** Feita. Só biblioteca padrão: OAuth 2.0 de app instalado com PKCE e redirecionamento para um servidor HTTP local de uma requisição só; token no keyring via `secret-tool` ou em arquivo 0600; API REST v3 com `singleEvents` para expandir recorrências e paginação. A sincronização lista os calendários de `config.toml` numa janela de um dia para trás e catorze para frente, troca os eventos `g:` do `state.json` e preserva os `l:`; em erro mantém os eventos antigos e grava `sync.status = "error"`. `agenda event add` cria no `write_calendar` quando o Google está configurado. O `agendad` roda como `systemd --user`: sincroniza a cada `sync_minutes`, avisa `minutes_before` minutos antes de cada evento com hora, lembra o que já avisou em `notified.json`, e manda o resumo em `morning_summary` uma vez por dia.
3. **Ponte de mensagens.** Telegram primeiro, por não precisar de URL pública; WhatsApp Cloud API com número dedicado depois. Interpretação por modelo de linguagem com três ferramentas: criar tarefa, criar evento, listar. O bot confirma antes de gravar.
4. **Publicação** em plugins.omarchy.org e dotfiles.

## Decisões tomadas

1. Subpassos com um nível só.
2. Concluir todos os subpassos não fecha a mãe.
3. Agenda como lista de dias, sem grade mensal, porque o relógio nativo já tem uma.
4. Quadrado fixo com rolagem interna.
5. Setas e h/l trocam de aba; Enter expande.
6. Id `pedro.agenda`, nome "Agenda".
7. Interface em português, sem camada de tradução por enquanto.
8. Prioridade com um nível só, marcada por `!`.

## Em aberto

- Edição do título na própria linha (tecla e). A CLI já tem `edit --title`; falta a interface.
- Menu de contexto no clique direito da linha.
- Desfazer para concluir, além de excluir.
- Entrada rápida global sem abrir o painel, como overlay.
- Ordem manual por arrastar.
