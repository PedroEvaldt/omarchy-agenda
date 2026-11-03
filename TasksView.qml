import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "Model.js" as Model

// Aba Tarefas: uma lista rolável com seções (Atrasadas, Hoje, Em breve, Sem
// data), cursor de teclado, subpassos recolhíveis e a seção Concluídas no fim.
//
// Recebe o painel (para cores, cursor e ações) e o ListModel já pronto pelo
// Model.rows(). Cada linha é uma tarefa, um subpasso ou o alternador das
// concluídas; o campo `kind` diz qual.
Item {
  id: view

  property var panel: null
  property alias model: list.model

  readonly property color fg: panel ? panel.fg : Commons.Color.foreground
  readonly property color dim: Qt.darker(fg, 1.5)
  readonly property string fontFamily: panel ? panel.fontFamily : Style.font.family

  ListView {
    id: list
    anchors.fill: parent
    clip: true
    spacing: Style.space(2)
    boundsBehavior: Flickable.StopAtBounds
    highlightFollowsCurrentItem: false
    currentIndex: view.panel ? view.panel.cursor : -1
    // O cursor do teclado nunca sai da área visível.
    onCurrentIndexChanged: if (currentIndex >= 0) positionViewAtIndex(currentIndex, ListView.Contain)

    section.property: "sectionKey"
    section.criteria: ViewSection.FullString
    section.delegate: Item {
      required property string section
      width: list.width
      // A seção das concluídas não tem cabeçalho: a própria linha
      // "Concluídas · N" faz esse papel.
      height: sectionText.text === "" ? 0 : Style.space(24)
      visible: height > 0

      PanelSectionHeader {
        id: sectionText
        anchors.left: parent.left
        anchors.leftMargin: Style.space(6)
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Style.space(3)
        text: Model.sectionLabel(section)
        foreground: view.fg
        fontFamily: view.fontFamily
      }
    }

    delegate: Item {
      id: row
      required property int index
      required property string kind
      required property string rowId
      required property string taskId
      required property string title
      required property bool done
      required property string dueLabel
      required property bool overdue
      required property bool hasSubs
      required property bool expanded
      required property int subDone
      required property int subTotal
      required property int depth

      readonly property bool isToggle: kind === "doneToggle"
      readonly property bool isSub: kind === "sub"
      readonly property bool current: view.panel !== null && view.panel.tab === 0 && view.panel.cursor === index

      width: list.width
      height: isSub ? Style.space(28) : Style.space(34)

      Rectangle {
        anchors.fill: parent
        radius: Style.cornerRadius
        color: row.current ? Style.selectedFill : (rowArea.containsMouse ? Style.hoverFill : "transparent")
      }

      // Chevron: só em tarefas com subpassos e no alternador das concluídas.
      Text {
        id: chevron
        x: Style.space(8) + row.depth * Style.space(22)
        width: Style.space(14)
        anchors.verticalCenter: parent.verticalCenter
        text: (row.hasSubs || row.isToggle) ? (row.expanded ? "󰅀" : "󰅂") : ""
        textFormat: Text.PlainText
        color: view.dim
        font.family: view.fontFamily
        font.pixelSize: Style.font.icon
      }

      // Caixa de marcar. Clicar nela conclui sem selecionar nem expandir.
      Text {
        id: box
        anchors.left: chevron.right
        anchors.leftMargin: Style.space(4)
        anchors.verticalCenter: parent.verticalCenter
        visible: !row.isToggle
        text: row.done ? "󰄲" : "󰄱"
        textFormat: Text.PlainText
        color: row.done ? Commons.Color.accent : view.fg
        font.family: view.fontFamily
        font.pixelSize: Style.font.icon

        MouseArea {
          anchors.fill: parent
          anchors.margins: -Style.space(4)
          cursorShape: Qt.PointingHandCursor
          onClicked: {
            if (!view.panel) return
            view.panel.cursor = row.index
            view.panel.toggleDone(list.model.get(row.index))
          }
        }
      }

      // Lixeira: aparece ao passar o mouse.
      Item {
        id: trash
        width: Style.space(22)
        height: parent.height
        anchors.right: parent.right
        anchors.rightMargin: Style.space(4)
        visible: !row.isToggle && (rowArea.containsMouse || trashArea.containsMouse)

        Text {
          anchors.centerIn: parent
          text: "󰆴"
          textFormat: Text.PlainText
          color: trashArea.containsMouse ? Commons.Color.urgent : view.dim
          font.family: view.fontFamily
          font.pixelSize: Style.font.bodySmall
        }

        MouseArea {
          id: trashArea
          anchors.fill: parent
          hoverEnabled: true
          cursorShape: Qt.PointingHandCursor
          onClicked: {
            if (!view.panel) return
            view.panel.cursor = row.index
            view.panel.removeCurrent()
          }
        }
      }

      // Prazo à direita; no alternador, o número de concluídas.
      Text {
        id: due
        anchors.right: trash.visible ? trash.left : parent.right
        anchors.rightMargin: Style.space(10)
        anchors.verticalCenter: parent.verticalCenter
        visible: text !== ""
        text: row.isToggle ? String(row.subTotal) : row.dueLabel
        textFormat: Text.PlainText
        color: row.overdue ? Commons.Color.urgent : view.dim
        font.family: view.fontFamily
        font.pixelSize: Style.font.caption
      }

      // Progresso dos subpassos, "2/4". Fica em destaque quando tudo está feito
      // e a tarefa mãe ainda está aberta: é o convite para bater o martelo.
      Text {
        id: counter
        anchors.right: due.visible ? due.left : (trash.visible ? trash.left : parent.right)
        anchors.rightMargin: Style.space(8)
        anchors.verticalCenter: parent.verticalCenter
        visible: text !== ""
        text: row.subTotal > 0 && !row.isToggle ? row.subDone + "/" + row.subTotal : ""
        textFormat: Text.PlainText
        color: row.subTotal > 0 && row.subDone === row.subTotal ? Commons.Color.accent : view.dim
        font.family: view.fontFamily
        font.pixelSize: Style.font.caption
      }

      Text {
        id: titleText
        anchors.left: row.isToggle ? chevron.right : box.right
        anchors.leftMargin: Style.space(8)
        anchors.right: counter.visible ? counter.left : (due.visible ? due.left : (trash.visible ? trash.left : parent.right))
        anchors.rightMargin: Style.space(8)
        anchors.verticalCenter: parent.verticalCenter
        text: row.title
        textFormat: Text.PlainText
        elide: Text.ElideRight
        color: row.done || row.isToggle ? view.dim : view.fg
        font.family: view.fontFamily
        font.pixelSize: row.isSub ? Style.font.bodySmall : Style.font.body
        font.strikeout: row.done && !row.isToggle

        PanelToolTip {
          visible: rowArea.containsMouse && titleText.truncated
          text: row.title
          fontFamily: view.fontFamily
        }
      }

      // Clique na linha: seleciona e expande ou recolhe. Fica abaixo da caixa
      // e da lixeira, que têm as próprias áreas.
      MouseArea {
        id: rowArea
        anchors.fill: parent
        z: -1
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        onClicked: {
          if (!view.panel) return
          view.panel.cursor = row.index
          view.panel.enterAction()
        }
      }
    }
  }

  Text {
    anchors.centerIn: parent
    width: parent.width - Style.space(40)
    visible: list.count === 0
    text: "Nada por fazer.\nEscreva abaixo, ou use `agenda add` no terminal."
    textFormat: Text.PlainText
    wrapMode: Text.WordWrap
    horizontalAlignment: Text.AlignHCenter
    color: view.dim
    font.family: view.fontFamily
    font.pixelSize: Style.font.body
    font.italic: true
  }
}
