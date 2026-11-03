import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// Botão do plugin Agenda na barra.
//
// Segue o mesmo contrato dos widgets nativos (relógio, clima): o widget é o
// dono do botão e carrega o painel (Panel.qml) por um Loader, injetando nele
// a barra, as configurações e o botão que serve de âncora. Tudo que o shell
// precisa para rotear `omarchy-shell shell toggle pedro.agenda '{}'` está
// aqui: open(), close() e a propriedade opened.
//
// O que aparece ao lado do ícone vem do painel (barLabel): o número de
// tarefas de hoje e atrasadas, ou o próximo evento quando falta menos de
// uma hora. Na barra vertical fica só o ícone.
//
// Usa WidgetButton, e não BarIconButton, porque o rótulo ao lado do ícone
// (labelText) só existe nas versões mais novas do shell; um texto simples
// com o glifo e o número funciona em todas.
BarWidget {
  id: root
  moduleName: "pedro.agenda"

  readonly property var panel: panelLoader.item
  readonly property bool opened: panel ? panel.opened === true : false
  readonly property bool popoutSwitchClosing: panel ? panel.popoutSwitchClosing === true : false
  readonly property string label: panel ? String(panel.barLabel || "") : ""
  readonly property string icon: "󰄲"

  // O painel nasce "cru" pelo Loader; a barra só chega depois, por isso a
  // injeção roda de novo sempre que bar ou settings mudam.
  function injectPanel() {
    var target = panelLoader.item
    if (!target) return
    if ("bar" in target) target.bar = root.bar
    if ("settings" in target) target.settings = root.settings
    if ("anchorItem" in target) target.anchorItem = button
    if ("hostWidget" in target) target.hostWidget = root
  }

  function open() { if (panel) panel.openFromHotkey() }
  function close() { if (panel) panel.close() }
  function toggle() { if (panel) panel.toggle() }
  function refresh() { if (panel) panel.reload() }
  function closeForPopoutSwitch() { if (panel) panel.closeForPopoutSwitch() }

  visible: true
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onBarChanged: injectPanel()
  onSettingsChanged: injectPanel()

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
    }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.vertical || root.label === "" ? root.icon : root.icon + " " + root.label
    horizontalMargin: 8.75
    verticalPadding: 8.75
    tooltipText: root.panel ? root.panel.tooltipText : "Agenda"
    // Tarefa atrasada pinta o botão com a cor de urgência do tema.
    active: root.panel ? root.panel.urgent === true : false

    onPressed: function(b) {
      if (!root.panel) return
      if (b === Qt.RightButton) root.panel.openForAdd()
      else if (b === Qt.MiddleButton) root.panel.sync()
      else root.panel.toggle()
    }
  }
}
