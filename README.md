# Agenda para o Omarchy

Plugin da barra do [Omarchy 4](https://omarchy.org) com um painel quadrado de duas abas: **Tarefas**, com subpassos, e **Agenda**, com os próximos dias. Por baixo, uma CLI em Python que é a única dona dos dados; no futuro, um serviço que sincroniza o Google Calendar e uma ponte para criar tarefas por mensagem.

Estado do projeto: **fase 1**, tarefas e eventos locais. Veja `SPEC.md` para o desenho completo e `docs/roadmap.md` para o plano de estudos e as fases.

## Instalar

```bash
omarchy plugin add https://github.com/PedroEvaldt/omarchy-agenda.git --enable
```

O Omarchy clona o repositório em `~/.config/omarchy/plugins/pedro.agenda/` e coloca o widget na barra, ao lado do relógio. Para mover:

```bash
omarchy bar move pedro.agenda --section right
```

Para ter a CLI à mão no terminal, crie um link ou um alias:

```bash
ln -s ~/.config/omarchy/plugins/pedro.agenda/bin/agenda ~/.local/bin/agenda
```

Para ver o painel cheio sem esforço, grave os dados de exemplo:

```bash
agenda seed
```

Requisitos: Omarchy 4 e Python 3.11 ou mais novo, que o Omarchy já traz.

## Usar

Clique no widget para abrir o painel. Clique direito abre já no campo de nova tarefa. Botão do meio recarrega o arquivo.

Atalho global, em `~/.config/hypr/bindings.lua`:

```lua
o.bind("SUPER + CTRL + T", nil, "omarchy-shell shell toggle pedro.agenda '{}'")
```

No painel:

| Tecla | Tarefas | Agenda |
|---|---|---|
| ← → ou h l, 1 2 | Troca de aba | Troca de aba |
| ↓ ↑ ou j k | Move o cursor | Move o cursor |
| Enter | Expande ou recolhe os subpassos | Abre o link do evento |
| Espaço | Conclui ou reabre | |
| a | Novo subpasso na tarefa selecionada | |
| d | Define o prazo da tarefa selecionada | |
| p | Adia um dia | |
| x ou Delete | Exclui, com Desfazer na notificação | |
| c | Mostra ou esconde as concluídas | |
| n ou / | Vai para o campo de entrada | |
| r | Recarrega | Recarrega |
| Esc | Sai do campo, senão fecha | Fecha |

O campo do rodapé entende datas em português:

| Você digita | Vira |
|---|---|
| comprar leite | tarefa sem data |
| pagar luz amanhã | tarefa com prazo amanhã |
| relatório sex ! | tarefa com prioridade, na sexta |
| dentista qui 15h | na aba Agenda, evento de uma hora |
| dentista qui 15h-16h30 | evento com fim explícito |

## CLI

```
agenda add "pagar luz amanhã" [--sub "x" --sub "y"] [--priority]
agenda done <id> | undo <id> | rm <id> | restore <id>
agenda sub add <id> "texto" | sub done <id.n> | sub undo <id.n> | sub rm <id.n>
agenda edit <id> --title "…" --due "sex" | --no-due
agenda snooze <id> [dias]
agenda list [--json] [--all]
agenda event add "dentista qui 15h" | event rm <id> | event list
agenda parse "texto"
agenda seed
agenda path
```

Os dados ficam em `~/.local/state/agenda/state.json`. O painel observa esse arquivo e atualiza sozinho; qualquer coisa que escreva nele pela CLI aparece na hora.

## Desenvolver

```bash
node --test tests/*.test.js
python3 -m pytest -q tests/
```

Com o repositório do Omarchy clonado ao lado, o validador oficial confere o manifest:

```bash
bash ../omarchy/bin/omarchy-plugin-validate .
```

Para desenvolver na própria máquina Omarchy, clone este repositório direto em `~/.config/omarchy/plugins/pedro.agenda` e habilite com `omarchy plugin enable pedro.agenda`. Salvar qualquer arquivo recarrega o plugin na hora.

## Licença

MIT.
