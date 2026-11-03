// Garante que o manifest e a fiação entre BarWidget e Panel seguem o contrato
// que o shell do Omarchy espera. Não substitui abrir o plugin de verdade.
const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")

const root = path.resolve(__dirname, "..")
const read = (name) => fs.readFileSync(path.join(root, name), "utf8")

function includes(source, fragment) {
  assert.equal(source.includes(fragment), true, `faltou: ${fragment}`)
}

test("manifest declara um bar-widget válido", () => {
  const manifest = JSON.parse(read("manifest.json"))
  assert.equal(manifest.schemaVersion, 1)
  assert.equal(manifest.id, "pedro.agenda")
  assert.equal(manifest.id.startsWith("omarchy."), false)
  assert.deepEqual(manifest.kinds, ["bar-widget"])
  assert.equal(fs.existsSync(path.join(root, manifest.entryPoints.barWidget)), true)
  for (const entry of manifest.barWidget.schema) assert.ok(entry.key in manifest.barWidget.defaults, entry.key)
})

test("BarWidget carrega o painel e expõe open/close/opened", () => {
  const widget = read("BarWidget.qml")
  includes(widget, 'moduleName: "pedro.agenda"')
  includes(widget, 'source: Qt.resolvedUrl("Panel.qml")')
  includes(widget, "target.bar = root.bar")
  includes(widget, "target.anchorItem = button")
  includes(widget, "target.hostWidget = root")
  includes(widget, "readonly property bool opened")
  includes(widget, "function open()")
  includes(widget, "function close()")
  includes(widget, "function closeForPopoutSwitch()")
})

test("Panel usa o tema qualificado e fala só com a CLI", () => {
  const panel = read("Panel.qml")
  includes(panel, "import qs.Commons as Commons")
  includes(panel, 'moduleName: "pedro.agenda"')
  includes(panel, "watchChanges: true")
  includes(panel, "cliProc.command = [cliPath].concat(args)")
  assert.equal(panel.includes("setText("), false, "o painel não escreve no state.json")
  for (const fn of ["openFromHotkey", "close", "toggle", "closeForPopoutSwitch", "switchPanel", "enterAction", "spaceAction", "submitField"])
    includes(panel, `function ${fn}(`)
})

test("nenhum QML usa Color sem o prefixo Commons", () => {
  for (const name of ["BarWidget.qml", "Panel.qml", "TasksView.qml", "AgendaView.qml"]) {
    const bare = read(name).match(/(^|[^.\w])Color\./g) || []
    assert.deepEqual(bare, [], `${name} usa Color sem Commons.`)
  }
})
