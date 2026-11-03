# Guia para agentes

Plugin da barra do Omarchy 4 (Quickshell/QML) com uma CLI em Python. Leia `SPEC.md` antes de mudar comportamento e `docs/roadmap.md` para entender em que fase o projeto está.

## Regras

- Comentários, textos de interface e mensagens de commit em português do Brasil.
- Indentação de dois espaços em QML, JS e JSON; quatro em Python.
- No QML, o tema é sempre `Commons.Color.*` (com `import qs.Commons as Commons`), nunca `Color.*` sem prefixo: o Qt 6.12 tem um tipo `Color` próprio.
- O painel nunca escreve no `state.json`. Toda escrita passa por `lib/agenda_ops.py`, que a CLI e a ponte de mensagens chamam.
- A ponte (`lib/agenda_bridge.py`) não conhece canal nenhum; o Telegram e qualquer canal futuro são tradutores à parte.
- Nada de polling em QML. O estado chega pelo `FileView` com `watchChanges`.
- Só biblioteca padrão do Python em `bin/agenda`, até que a fase 2 justifique dependências.

## Testes

```bash
node --test tests/*.test.js
python3 -m pytest -q tests/
```

Validação do manifest com o script do próprio Omarchy, quando o repositório dele estiver clonado ao lado:

```bash
bash ../omacom/omarchy/bin/omarchy-plugin-validate .
```

QML não roda fora do Omarchy. `pyside6-qmllint` (pacote PySide6-Essentials) pega erros de sintaxe; os avisos sobre módulos `qs.*` e `Quickshell` desconhecidos são esperados.

## Referências

- Manual do Omarchy, capítulo 32 (plugins do shell) e `docs/omarchy-shell.md` no repositório `omacom/omarchy`.
- Plugins nativos que servem de modelo: `shell/plugins/panels/clock`, `weather` e `tailscale`.
