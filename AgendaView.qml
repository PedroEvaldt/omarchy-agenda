import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "Model.js" as Model

// Aba Agenda: os próximos dias em lista, um cabeçalho por dia, eventos de
// dia todo primeiro. Dias vazios mostram "nada marcado" para a semana não
// parecer mais cheia do que é.
//
// Na fase 1 os eventos vêm do state.json local; na fase 2 o serviço de
// sincronização passa a escrever ali os eventos do Google Calendar e nada
// aqui precisa mudar.
Item {
  id: view

  property var panel: null
  property alias model: list.model

  readonly property color fg: panel ? panel.fg : Commons.Color.foreground
  readonly property color dim: Qt.darker(fg, 1.5)
  readonly property string fontFamily: panel ? panel.fontFamily : Style.font.family
  readonly property string todayKey: panel ? panel.todayKey : Model.dateKey(new Date())

  ListView {
    id: list
    anchors.fill: parent
    clip: true
    spacing: Style.space(2)
    boundsBehavior: Flickable.StopAtBounds
    highlightFollowsCurrentItem: false
    currentIndex: view.panel ? view.panel.cursor : -1
    onCurrentIndexChanged: if (currentIndex >= 0) positionViewAtIndex(currentIndex, ListView.Contain)

    section.property: "sectionKey"
    section.criteria: ViewSection.FullString
    section.delegate: Item {
      required property string section
      width: list.width
      height: Style.space(24)

      PanelSectionHeader {
        anchors.left: parent.left
        anchors.leftMargin: Style.space(6)
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Style.space(3)
        text: Model.dayLabel(section, view.todayKey)
        foreground: view.fg
        fontFamily: view.fontFamily
      }
    }

    delegate: Item {
      id: row
      required property int index
      required property string kind
      required property string rowId
      required property string title
      required property string timeLabel
      required property string location
      required property string url
      required property bool past
      required property string color

      readonly property bool isEmpty: kind === "empty"
      readonly property bool current: view.panel !== null && view.panel.tab === 1 && view.panel.cursor === index

      width: list.width
      height: Style.space(30)
      opacity: past ? 0.5 : 1

      Rectangle {
        anchors.fill: parent
        radius: Style.cornerRadius
        color: row.current ? Style.selectedFill : (rowArea.containsMouse ? Style.hoverFill : "transparent")
      }

      // Pontinho na cor do calendário de origem, quando houver.
      Rectangle {
        id: dot
        width: Style.space(6)
        height: width
        radius: width / 2
        anchors.left: parent.left
        anchors.leftMargin: Style.space(8)
        anchors.verticalCenter: parent.verticalCenter
        visible: !row.isEmpty && row.color !== ""
        color: row.color !== "" ? row.color : "transparent"
      }

      Text {
        id: timeText
        anchors.left: parent.left
        anchors.leftMargin: Style.space(20)
        anchors.verticalCenter: parent.verticalCenter
        width: Style.space(86)
        text: row.timeLabel
        textFormat: Text.PlainText
        color: view.dim
        font.family: view.fontFamily
        font.pixelSize: Style.font.caption
      }

      Text {
        id: placeText
        anchors.right: parent.right
        anchors.rightMargin: Style.space(10)
        anchors.verticalCenter: parent.verticalCenter
        visible: text !== ""
        text: row.location !== "" ? row.location : (row.url !== "" ? "󰖟" : "")
        textFormat: Text.PlainText
        elide: Text.ElideRight
        width: Math.min(implicitWidth, Style.space(110))
        color: view.dim
        font.family: view.fontFamily
        font.pixelSize: Style.font.caption
      }

      Text {
        id: titleText
        anchors.left: timeText.right
        anchors.leftMargin: Style.space(6)
        anchors.right: placeText.visible ? placeText.left : parent.right
        anchors.rightMargin: Style.space(8)
        anchors.verticalCenter: parent.verticalCenter
        text: row.title
        textFormat: Text.PlainText
        elide: Text.ElideRight
        color: row.isEmpty ? view.dim : view.fg
        font.family: view.fontFamily
        font.pixelSize: row.isEmpty ? Style.font.bodySmall : Style.font.body
        font.italic: row.isEmpty

        PanelToolTip {
          visible: rowArea.containsMouse && (titleText.truncated || row.url !== "")
          text: row.url !== "" ? row.title + "\n" + row.url : row.title
          fontFamily: view.fontFamily
        }
      }

      MouseArea {
        id: rowArea
        anchors.fill: parent
        z: -1
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        onClicked: {
          if (!view.panel || row.isEmpty) return
          view.panel.cursor = row.index
          view.panel.enterAction()
        }
      }
    }
  }
}
