# Roadmap de estudos: plugin Agenda para o Omarchy 4

Projeto: um plugin da barra do Omarchy 4 com um painel quadrado de duas abas, Tarefas e Agenda, alimentado por um serviço local em Python que sincroniza o Google Calendar e, no futuro, recebe tarefas e eventos por mensagem no WhatsApp.

Dois fatos que moldam a lista: a lógica dentro de QML é JavaScript, então JavaScript básico vem antes de QML. E no Omarchy 4 a configuração do Hyprland, incluindo atalhos e autostart, é em Lua, então um pouco de Lua entra também.

Profundidade de cada item:

- **leve**: assistir e entender
- **média**: fazer exercícios
- **funda**: onde o projeto realmente vive
- **comigo**: não há vídeo bom, aprendemos juntos na hora de usar

Todos os links abaixo foram conferidos no YouTube, com título e canal reais, em novembro de 2026.

---

## Etapa 0. Base de terminal

Se já domina, pule.

| Tema | Profundidade | Por que | Vídeos |
|---|---|---|---|
| Bash | média | A CLI de cola do projeto e todos os helpers do Omarchy são bash | [The Complete Bash Scripting Course, You Suck at Programming](https://www.youtube.com/watch?v=Sx9zG7wa4FA) · [Bash Scripting on Linux, Learn Linux TV](https://www.youtube.com/playlist?list=PLT98CRl2KxKGj-VKtApD8-zCqSaN2mD4w) |
| JSON e jq | leve | O estado do plugin, o manifest e a configuração do shell são JSON | [jq JSON Processor Tutorial, Code With Bubb](https://www.youtube.com/watch?v=EvpwhGeiH0U) · [jq: A Practical Guide, Navek](https://www.youtube.com/watch?v=j7xZ2VkLYIY) |
| Git e GitHub | média | O plugin é distribuído como repositório git e o Omarchy instala direto dele | [Curso de Git e GitHub, Curso em Vídeo](https://www.youtube.com/playlist?list=PLHz_AreHm4dm7ZULPAmadvNhH6vk9oNZA) · [Curso Completo de Git e GitHub, Stack Mobile](https://www.youtube.com/watch?v=LeAEMvHEx4o) |

## Etapa 1. Omarchy por dentro

Uma semana, leve, mas obrigatória antes de qualquer código.

| Tema | Profundidade | Por que | Vídeos |
|---|---|---|---|
| Visão geral do Quattro | leve | Entender que a barra é um processo Quickshell e tudo é plugin | [Omarchy Quattro, DHH](https://www.youtube.com/watch?v=F7fe9pa8OeE) · [Your Desktop Is Now A Programmable Playground, NO SIGNAL](https://www.youtube.com/watch?v=PYkRUL3TlqY) |
| Sistema de plugins na prática | leve | Ver o fluxo de instalar, habilitar e recarregar | [Customize Omarchy 4.0 with Plugins, TechWorld](https://www.youtube.com/watch?v=zOrs7v2kE7c) · [Watch Me Build An Omarchy Quattro Plugin in 12 Minutes, NO SIGNAL](https://www.youtube.com/watch?v=_6vWWz6Oipk) (usa IA para escrever o código; assista pelo fluxo, não pelo QML) |
| Leitura obrigatória | comigo | Capítulos do manual oficial: a barra, atalhos, dotfiles e plugins do shell. Depois a referência técnica do shell e o catálogo de plugins nativos. Tudo no repositório do Omarchy | sem vídeo |
| Lua básico | leve | Só o suficiente para editar `~/.config/hypr/bindings.lua` e `autostart.lua` | [Learn Lua Language in 10 Minutes, AmanBytes](https://www.youtube.com/watch?v=xiH9ZEof_NA) · [Lua Tutorial for Beginners, Codynn](https://www.youtube.com/watch?v=9u0TdPP2ugE) |

## Etapa 2. QML e Quickshell

O coração do painel. Três a quatro semanas, funda.

| Tema | Profundidade | Por que | Vídeos |
|---|---|---|---|
| JavaScript básico | média | Variáveis, funções, arrays, objetos, JSON, datas. É a linguagem das funções dentro do QML. Ignore as partes de página web e DOM | [Curso Grátis de JavaScript e ECMAScript, Curso em Vídeo](https://www.youtube.com/playlist?list=PLHz_AreHm4dlsK3Nr9GVvXCbpQyHQl1o1) |
| QML fundamentos | funda | Itens, anchors, layouts, propriedades e bindings, sinais, ListView com modelo e delegate, Loader, estados e animações. Não precisa dos vídeos de C++ | [Introduction to Qt Quick and QML, curso completo da KDAB](https://www.youtube.com/playlist?list=PL6CJYn40gN6hdNC1IGQZfVI707dh9DPRc), começando pela [parte 1](https://www.youtube.com/watch?v=JxyTkXLbcV4) · para o vocabulário: [Qt 6 For Beginners, introdução a QtQuick e QML, Misha dev Diary](https://www.youtube.com/watch?v=eP0l0Px8OJM) |
| Quickshell | média | Janelas de layer shell, PanelWindow, executar processos, ler arquivos com watch, IPC. Nenhum vídeo é sobre Omarchy; servem para entender a ferramenta por baixo | [How to Install and Configure Quickshell, tony](https://www.youtube.com/watch?v=g_I4hwCuDyQ) · [Building a Complete Desktop Shell in Quickshell QML, Paul Yu](https://www.youtube.com/watch?v=YQxrh5_naMQ) · [Hyprland Quickshell Tutorials, Mattscreative](https://www.youtube.com/playlist?list=PLd2rY36Ym3b_MNFiChJ-KKuwlWg6TlSP8) |
| Componentes do Omarchy | comigo | BarWidget, Panel, KeyboardPanel, tokens de tema e o padrão "widget mais painel". Vamos ler juntos o código do relógio, do clima e do Tailscale, os três exemplos do que você quer fazer | sem vídeo |

## Etapa 3. Python para o serviço

Duas a três semanas, funda.

| Tema | Profundidade | Por que | Vídeos |
|---|---|---|---|
| Python | média a funda | O daemon, a CLI e a ponte de mensagens | Começando do zero: [Curso de Python 3, Mundo 1](https://www.youtube.com/playlist?list=PLHz_AreHm4dlKP6QQCekuIPky1CiwmdI6), [Mundo 2](https://www.youtube.com/playlist?list=PLHz_AreHm4dk_nZHmxxf_J0WRAqy5Czye) e [Mundo 3](https://www.youtube.com/playlist?list=PLHz_AreHm4dksnH2jVTIVNviIMBVYyFnH), Curso em Vídeo · já programa: [Curso Completo de Python, Bóson Treinamentos](https://www.youtube.com/watch?v=-VeVq64Fgw0) como revisão |
| SQLite com Python | média | O banco das tarefas | [Python SQLite Tutorial, Corey Schafer](https://www.youtube.com/watch?v=pd-0G0MigUA) · versão longa: [SQLite Databases With Python, freeCodeCamp](https://www.youtube.com/watch?v=byHcYRpMgI4) |
| Argparse, dataclasses, logging, datetime com fuso, dateparser em português, ambiente virtual | comigo | Cada peça entra quando for escrita | sem vídeo |
| systemd de usuário | leve | O daemon roda como serviço seu, sem root. A parte de `systemctl --user` fica comigo | [How to Use Systemd Timers, Luke](https://www.youtube.com/watch?v=2XuDmdNX6zU) · [Systemd Timers, Nerd on the Street](https://www.youtube.com/watch?v=Oup21KLlpD8) |

## Etapa 4. Google Calendar

Uma semana, média.

| Tema | Profundidade | Por que | Vídeos |
|---|---|---|---|
| OAuth 2.0 | leve | Entender o conceito evita horas de confusão com tokens | [OAuth 2.0: Why Every App Uses This Instead of Passwords, Trust Boundary](https://www.youtube.com/watch?v=U8neDKIinIw) · [OAuth 2.0 explained with examples, ByteMonk](https://www.youtube.com/watch?v=ZDuRmhLSLOY) · clássico, com alguns detalhes antigos: [OAuth 2.0 and OpenID Connect, OktaDev](https://www.youtube.com/watch?v=996OiexHze0) |
| API do Calendar em Python | média | Ler e depois escrever eventos | [Google Calendar API in Python, Getting Started, Jie Jenn](https://www.youtube.com/watch?v=1JkKtGFnua8) · [Create Events Using OAuth2.0, Ninja Guides](https://www.youtube.com/watch?v=ZbjbFWAwL6g) · [Create Events and Check Free Slots, Raj Kapadia](https://www.youtube.com/watch?v=vEJ8Tf2pc3s) |
| Eventos recorrentes, token no keyring | comigo | Detalhes que os vídeos não cobrem | sem vídeo |

## Etapa 5. Ponte de mensagens

Duas semanas, média.

| Tema | Profundidade | Por que | Vídeos |
|---|---|---|---|
| HTTP e webhooks com FastAPI | média | Receber mensagens do WhatsApp | [Python FastAPI Tutorial Part 1, Corey Schafer](https://www.youtube.com/watch?v=7AMjmCTumuo) |
| Bot de Telegram | leve | O protótipo sem URL pública | [How To Create A Telegram Bot In Python, Indently](https://www.youtube.com/watch?v=vZtm1wuA2yc) |
| WhatsApp Cloud API | média | O canal final | [WhatsApp Cloud API Webhook Setup from Meta App, WebTopTemp](https://www.youtube.com/watch?v=N5LLmBtcfCs) |
| Expor o webhook | leve | Cloudflare Tunnel ou Tailscale Funnel. A documentação da Cloudflare é curta e é a referência principal | [How to Expose Local Host using Cloudflare Tunnels, Piyush Garg](https://www.youtube.com/watch?v=BnWfbv7Fy-k) |
| Tool use com modelo de linguagem | média | Transformar "dentista qui 15h" em evento | [Getting Started with Tool Use in the Anthropic API, Ram Vegiraju](https://www.youtube.com/watch?v=7xVmf9lIj14) · [Claude Function Calling Made Dead Simple, Nodematic](https://www.youtube.com/watch?v=2HsmNeT8TCg) · conceito geral: [Function calling and structured outputs, Microsoft Reactor](https://www.youtube.com/watch?v=4rFVLMBwjGY) |
| Desenho das ferramentas e fluxo de confirmação | comigo | Específico do projeto | sem vídeo |

## Etapa 6. Acabamento

Comigo, sem vídeo, é curto: testes com pytest, segredos fora do git, README, publicar no marketplace plugins.omarchy.org.

---

## Resumo

| Etapa | Semanas aproximadas | Peso no projeto |
|---|---|---|
| 0. Base de terminal | 1 a 2 | Apoio |
| 1. Omarchy por dentro | 1 | Obrigatória |
| 2. QML e Quickshell | 3 a 4 | O painel inteiro |
| 3. Python e serviço | 2 a 3 | Dados e CLI |
| 4. Google Calendar | 1 | Aba Agenda |
| 5. Ponte de mensagens | 2 | WhatsApp |
| 6. Acabamento | 1 | Publicação |

## Como usar

Não assista tudo antes de codar. A ordem bate com as fases do projeto, então o ideal é intercalar: termina a etapa 2 e já constrói a aba de tarefas com dados falsos num arquivo JSON. Termina a etapa 3 e troca o arquivo falso pelo serviço de verdade. Cada etapa produz uma peça que funciona sozinha.

Dois cuidados com os vídeos de QML e Quickshell: nenhum deles usa os componentes do Omarchy, então o que você aprende lá é a linguagem e a ferramenta; a camada do Omarchy a gente aprende lendo o código do próprio shell. E os vídeos de Quickshell mostram setups completos de barra: assista pela compreensão de como as peças se encaixam, sem tentar reproduzir.

## Referências escritas

- Manual do Omarchy, no repositório `omacom/omarchy`, pasta `manual/`: capítulos 05 (a barra), 07 (atalhos), 31 (dotfiles) e 32 (plugins do shell)
- Referência técnica do shell: `docs/omarchy-shell.md` no mesmo repositório
- Catálogo dos plugins nativos: `shell/plugins/README.md`
- Documentação do Quickshell: https://quickshell.org
- Documentação de QML: https://doc.qt.io
- Quickstart oficial do Google Calendar em Python, na documentação do Google
- Documentação de tool use da Anthropic
- Marketplace de plugins: https://plugins.omarchy.org
