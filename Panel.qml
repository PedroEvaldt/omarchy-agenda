import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "Model.js" as Model

// O painel quadrado do plugin Agenda.
//
// Duas abas, Tarefas e Agenda, trocadas pelas setas do cabeçalho ou pelas
// teclas ← → (h l). O corpo rola; o rodapé tem o campo de entrada rápida.
//
// Fluxo de dados, de propósito bem simples:
//   state.json  --FileView (watch)-->  state  --Model.js-->  ListModels  -->  telas
//   telas  --Process-->  bin/agenda  --escreve-->  state.json
// O painel nunca escreve no arquivo: toda ação vira um comando da CLI, e a
// mudança volta pelo FileView. Assim terminal, painel e, no futuro, o
// WhatsApp entram pela mesma porta.
Panel {
  id: root
  moduleName: "pedro.agenda"

  // Injetados pelo BarWidget depois que o Loader cria este item.
  property var anchorItem: null
  property var hostWidget: null
  // A barra identifica o painel pelo widget montado no slot dela, não por
  // este item aninhado; é com isso que ela fecha o popup anterior ao abrir
  // outro e desenha o ponto de "painel aberto" sob o ícone.
  readonly property var barIdentity: hostWidget || root

  // Cores e fonte vindas da barra, com o tema como reserva enquanto a barra
  // ainda não foi injetada.
  readonly property color fg: bar ? bar.foreground : Commons.Color.foreground
  readonly property color dim: Qt.darker(fg, 1.5)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family

  // ---- Arquivos -------------------------------------------------------------
  readonly property string home: Quickshell.env("HOME")
  readonly property string stateDir: (Quickshell.env("XDG_STATE_HOME") || (home + "/.local/state")) + "/agenda"
  readonly property string statePath: stateDir + "/state.json"
  readonly property string configuredCli: String(setting("cliPath", "") || "")
  // Plugins instalados pelo Omarchy moram em ~/.config/omarchy/plugins/<id>/,
  // então a CLI que vem junto no repositório tem um caminho previsível.
  readonly property string cliPath: configuredCli !== "" ? configuredCli : home + "/.config/omarchy/plugins/pedro.agenda/bin/agenda"

  // ---- Estado ---------------------------------------------------------------
  property var state: Model.emptyState()
  property date now: new Date()
  readonly property string todayKey: Model.dateKey(now)
  // Quais tarefas estão com os subpassos abertos, por id. Fica na memória
  // do painel: reabrir mostra como você deixou.
  property var expanded: ({})
  property bool showCompleted: setting("showCompleted", false) === true
  readonly property int agendaDays: Math.max(1, Math.min(30, parseInt(String(setting("agendaDays", 7)), 10) || 7))
  property int tab: String(setting("defaultTab", "tasks")) === "agenda" ? 1 : 0
  property int cursor: 0
  property bool enterPending: false
  // O campo do rodapé muda de função: "add" cria tarefa, "sub" cria subpasso
  // da tarefa selecionada, "due" define o prazo dela.
  property string fieldMode: "add"
  property string fieldTarget: ""
  property string lastError: ""
  property bool cliBusy: false
  property var cliQueue: []

  readonly property var counts: Model.counts(state, todayKey)
  readonly property bool urgent: counts.overdue > 0
  readonly property string barLabel: Model.barLabel(state, now)
  readonly property string tooltipText: Model.tooltip(state, now)
  readonly property string syncText: Model.syncLabel(state.sync)
  readonly property string tabTitle: tab === 0 ? "TAREFAS" : "AGENDA"
  readonly property int rowCount: tab === 0 ? taskRows.count : eventRows.count
  readonly property string fieldPlaceholder: tab === 1 ? "+ novo evento…"
    : fieldMode === "sub" ? "+ subpasso…"
    : fieldMode === "due" ? "prazo: amanhã, sex, 12/11…"
    : "+ nova tarefa…"

  ListModel { id: taskRows }
  ListModel { id: eventRows }

  // Refaz as listas a partir do estado. Barato o bastante para rodar a cada
  // mudança: são dezenas de linhas, não milhares.
  function rebuild() {
    fillModel(taskRows, Model.rows(state, { todayKey: todayKey, expanded: expanded, showCompleted: showCompleted }))
    fillModel(eventRows, Model.eventRows(state, { todayKey: todayKey, days: agendaDays, now: now }))
    if (cursor >= rowCount) cursor = Math.max(0, rowCount - 1)
  }

  function fillModel(model, list) {
    model.clear()
    for (var i = 0; i < list.length; i++) model.append(list[i])
  }

  onStateChanged: rebuild()
  onExpandedChanged: rebuild()
  onShowCompletedChanged: rebuild()
  onTodayKeyChanged: rebuild()
  onAgendaDaysChanged: rebuild()
  onTabChanged: cursor = 0
  Component.onCompleted: {
    rebuild()
    ensureDirs.running = true
  }

  function applyState(raw) { state = Model.parseState(raw) }
  function reload() { stateFile.reload() }

  // ---- Cursor e abas --------------------------------------------------------
  function currentRow() {
    var model = tab === 0 ? taskRows : eventRows
    return cursor >= 0 && cursor < model.count ? model.get(cursor) : null
  }

  function moveCursor(dy) {
    if (rowCount === 0) { cursor = 0; return }
    cursor = Math.max(0, Math.min(rowCount - 1, cursor + dy))
  }

  function setTab(next) { tab = ((next % 2) + 2) % 2 }

  function toggleExpanded(taskId) {
    var copy = {}
    for (var key in expanded) copy[key] = expanded[key]
    if (copy[taskId]) delete copy[taskId]
    else copy[taskId] = true
    expanded = copy
  }

  // Enter: expande ou recolhe na aba Tarefas; abre o link na Agenda.
  function enterAction() {
    var row = currentRow()
    if (!row) return
    if (tab === 0) {
      if (row.kind === "doneToggle") showCompleted = !showCompleted
      else if (row.kind === "task" && row.hasSubs) toggleExpanded(row.taskId)
    } else if (row.kind === "event" && row.url !== "") {
      openUrl(row.url)
    }
  }

  // Espaço: conclui ou reabre a linha sob o cursor.
  function spaceAction() {
    var row = currentRow()
    if (!row || tab !== 0) return
    if (row.kind === "doneToggle") showCompleted = !showCompleted
    else toggleDone(row)
  }

  function toggleDone(row) {
    if (row.kind === "task") runCli([row.done ? "undo" : "done", row.taskId])
    else if (row.kind === "sub") runCli(["sub", row.done ? "undo" : "done", row.rowId])
  }

  function removeCurrent() {
    var row = currentRow()
    if (!row || tab !== 0) return
    if (row.kind === "task") runCli(["rm", row.taskId])
    else if (row.kind === "sub") runCli(["sub", "rm", row.rowId])
  }

  function snoozeCurrent() {
    var row = currentRow()
    if (row && tab === 0 && row.kind === "task") runCli(["snooze", row.taskId])
  }

  function openUrl(url) {
    if (bar && typeof bar.run === "function") bar.run("xdg-open " + Util.shellQuote(url))
  }

  // ---- Campo do rodapé ------------------------------------------------------
  function startAdd() {
    fieldMode = "add"
    fieldTarget = ""
    focusField()
  }

  function startSub() {
    var row = currentRow()
    if (!row || tab !== 0 || row.kind === "doneToggle") return
    fieldMode = "sub"
    fieldTarget = row.taskId
    focusField()
  }

  function startDue() {
    var row = currentRow()
    if (!row || tab !== 0 || row.kind !== "task") return
    fieldMode = "due"
    fieldTarget = row.taskId
    focusField()
  }

  function focusField() {
    field.forceActiveFocus()
    field.selectAll()
  }

  function leaveField() {
    field.clear()
    fieldMode = "add"
    fieldTarget = ""
    keyCatcher.forceActiveFocus()
  }

  function submitField() {
    var text = String(field.text).trim()
    if (text === "") { leaveField(); return }
    if (tab === 1) runCli(["event", "add", text])
    else if (fieldMode === "sub") runCli(["sub", "add", fieldTarget, text])
    else if (fieldMode === "due") runCli(["edit", fieldTarget, "--due", text])
    else runCli(["add", text])
    field.clear()
    // Subpasso e prazo são ações de uma vez só: o foco volta para a lista.
    // Nova tarefa fica no campo, para emendar a próxima.
    if (fieldMode !== "add") leaveField()
  }

  // ---- CLI ------------------------------------------------------------------
  // Uma fila simples: um comando por vez, na ordem em que foram pedidos.
  function runCli(args) {
    var next = cliQueue.slice()
    next.push(args)
    cliQueue = next
    drainCli()
  }

  function drainCli() {
    if (cliBusy || cliQueue.length === 0) return
    var args = cliQueue[0]
    cliQueue = cliQueue.slice(1)
    cliBusy = true
    cliProc.command = [cliPath].concat(args)
    cliProc.running = true
  }

  Process {
    id: cliProc
    running: false
    stdout: StdioCollector { waitForEnd: true }
    stderr: StdioCollector {
      id: cliErr
      waitForEnd: true
    }
    onExited: function(exitCode) {
      root.cliBusy = false
      root.lastError = exitCode === 0 ? "" : (String(cliErr.text || "").trim() || ("agenda saiu com código " + exitCode))
      root.drainCli()
    }
  }

  Process {
    id: ensureDirs
    command: ["mkdir", "-p", root.stateDir]
    onExited: stateFile.reload()
  }

  // O arquivo é a fonte de verdade: qualquer escrita, de onde vier, chega
  // aqui por este watch. Sem polling.
  FileView {
    id: stateFile
    path: root.statePath
    watchChanges: true
    printErrors: false
    onLoaded: root.applyState(text())
    onLoadFailed: root.applyState("")
    onFileChanged: reload()
  }

  // Relógio de minuto em minuto: muda o dia à meia-noite e o "próximo evento".
  SystemClock {
    id: clock
    precision: SystemClock.Minutes
    onDateChanged: root.now = date
  }

  // ---- Ciclo de vida --------------------------------------------------------
  function openFromHotkey() {
    root.controller.show()
    Qt.callLater(function() {
      if (root.opened) root.setCenterHoverRevealSuppressed(true)
    })
  }

  function openForAdd() {
    openFromHotkey()
    Qt.callLater(function() {
      if (root.opened) root.startAdd()
    })
  }

  function close() {
    setCenterHoverRevealSuppressed(false)
    root.controller.hide()
  }

  function toggle() {
    if (root.opened) root.close()
    else root.openFromHotkey()
  }

  function closeForPopoutSwitch() { root.close() }

  function switchPanel(direction) {
    if (root.bar && typeof root.bar.switchPanelFrom === "function")
      return root.bar.switchPanelFrom(root.barIdentity, direction)
    return false
  }

  function setCenterHoverRevealSuppressed(value) {
    if (root.bar && typeof root.bar.setCenterHoverRevealSuppressed === "function")
      root.bar.setCenterHoverRevealSuppressed(value)
  }

  // ---- A janela -------------------------------------------------------------
  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    centerOnBar: false
    focusTarget: keyCatcher
    // Quadrado de verdade: a altura é a largura, e o que não cabe rola.
    contentWidth: panel.fittedContentWidth(Style.space(420))
    contentHeight: panel.cappedContentHeight(panel.contentWidth)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      blocked: field.activeFocus

      onMoveRequested: function(dx, dy) {
        if (dx !== 0) root.setTab(root.tab + dx)
        if (dy !== 0) root.moveCursor(dy)
      }
      // Enter dispara returnRequested e logo depois activateRequested;
      // Espaço dispara só activateRequested. A flag separa os dois.
      onReturnRequested: root.enterPending = true
      onActivateRequested: {
        var wasEnter = root.enterPending
        root.enterPending = false
        if (wasEnter) root.enterAction()
        else root.spaceAction()
      }
      onCloseRequested: root.close()
      onDeleteRequested: root.removeCurrent()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) {
        if (t === "n" || t === "/") root.startAdd()
        else if (t === "a") root.startSub()
        else if (t === "d") root.startDue()
        else if (t === "p") root.snoozeCurrent()
        else if (t === "c") root.showCompleted = !root.showCompleted
        else if (t === "r") root.reload()
        else if (t === "1") root.setTab(0)
        else if (t === "2") root.setTab(1)
      }

      // ---- Cabeçalho: seta, título da aba, seta ----
      Item {
        id: header
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: Style.space(40)

        Button {
          anchors.left: parent.left
          anchors.verticalCenter: parent.verticalCenter
          iconText: "󰅁"
          foreground: root.fg
          tooltipText: "Aba anterior"
          onClicked: root.setTab(root.tab - 1)
        }

        Column {
          anchors.centerIn: parent
          spacing: Style.space(2)

          Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.tabTitle
            textFormat: Text.PlainText
            color: root.fg
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            font.bold: true
            font.letterSpacing: 1
          }

          Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.tab === 0 ? "● ○" : "○ ●"
            textFormat: Text.PlainText
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }
        }

        Button {
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          iconText: "󰅂"
          foreground: root.fg
          tooltipText: "Próxima aba"
          onClicked: root.setTab(root.tab + 1)
        }
      }

      PanelSeparator {
        id: headerLine
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        foreground: root.fg
      }

      // ---- Corpo: as duas abas lado a lado num trilho que desliza ----
      Item {
        id: body
        anchors.top: headerLine.bottom
        anchors.bottom: footerLine.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.topMargin: Style.space(6)
        anchors.bottomMargin: Style.space(6)
        clip: true

        Item {
          id: track
          width: body.width * 2
          height: body.height
          x: -root.tab * body.width

          // Style.duration só existe nas versões mais novas do shell (respeita o
          // "animações desligadas" do Omarchy); na 4.0.x cai no valor fixo.
          Behavior on x {
            NumberAnimation {
              duration: typeof Style.duration === "function" ? Style.duration(200) : 200
              easing.type: Easing.OutCubic
            }
          }

          TasksView {
            x: 0
            width: body.width
            height: body.height
            panel: root
            model: taskRows
          }

          AgendaView {
            x: body.width
            width: body.width
            height: body.height
            panel: root
            model: eventRows
          }
        }
      }

      PanelSeparator {
        id: footerLine
        anchors.bottom: footer.top
        anchors.left: parent.left
        anchors.right: parent.right
        foreground: root.fg
      }

      // ---- Rodapé: entrada rápida e estado da sincronização ----
      Item {
        id: footer
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        height: Style.space(40)

        TextField {
          id: field
          anchors.left: parent.left
          anchors.right: status.left
          anchors.rightMargin: Style.space(10)
          anchors.verticalCenter: parent.verticalCenter
          placeholderText: root.fieldPlaceholder
          foreground: root.fg
          font.family: root.fontFamily

          Keys.onPressed: function(event) {
            if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
              root.submitField()
              event.accepted = true
            } else if (event.key === Qt.Key_Escape) {
              if (String(field.text) !== "") field.clear()
              else root.leaveField()
              event.accepted = true
            } else if (event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab) {
              event.accepted = true
            }
          }
        }

        Text {
          id: status
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          text: root.lastError !== "" ? "erro" : root.syncText
          textFormat: Text.PlainText
          color: root.lastError !== "" ? Commons.Color.urgent : root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption

          MouseArea {
            id: statusArea
            anchors.fill: parent
            anchors.margins: -Style.space(4)
            hoverEnabled: true

            PanelToolTip {
              visible: statusArea.containsMouse && root.lastError !== ""
              text: root.lastError
              fontFamily: root.fontFamily
            }
          }
        }
      }
    }
  }
}
