// Testes do Model.js: rodam com `node --test tests/` e não precisam de Qt.
const test = require("node:test")
const assert = require("node:assert/strict")
const Model = require("../Model.js")

const TODAY = "2026-11-03" // terça-feira

function state(tasks, events) {
  return Model.parseState(JSON.stringify({ tasks: tasks || [], events: events || [] }))
}

test("parseState aceita arquivo vazio, inválido e sem campos", () => {
  assert.deepEqual(Model.parseState("").tasks, [])
  assert.deepEqual(Model.parseState("{nope").events, [])
  assert.equal(Model.parseState("{}").sync.status, "none")
})

test("parseState descarta tarefas sem título ou sem id e normaliza subpassos", () => {
  const s = state([
    { id: "a1", title: "  ok  ", subtasks: [{ title: "x" }, { title: "" }, { id: "a1.9", title: "y", done: true }] },
    { id: "", title: "sem id" },
    { id: "b2", title: "" },
  ])
  assert.equal(s.tasks.length, 1)
  assert.equal(s.tasks[0].title, "ok")
  assert.deepEqual(s.tasks[0].subtasks.map(x => x.id), ["a1.1", "a1.9"])
})

test("classify separa atrasadas, hoje, em breve, sem data e concluídas", () => {
  const mk = (due, completedAt) => ({ due, dueTime: "", completedAt: completedAt || "", subtasks: [] })
  assert.equal(Model.classify(mk("2026-11-02"), TODAY), "overdue")
  assert.equal(Model.classify(mk("2026-11-03"), TODAY), "today")
  assert.equal(Model.classify(mk("2026-11-10"), TODAY), "soon")
  assert.equal(Model.classify(mk(""), TODAY), "nodate")
  assert.equal(Model.classify(mk("2026-11-01", "2026-11-02T10:00:00"), TODAY), "done")
})

test("dueLabel fala português curto", () => {
  const mk = (due, dueTime) => ({ due, dueTime: dueTime || "" })
  assert.equal(Model.dueLabel(mk("2026-11-03"), TODAY), "hoje")
  assert.equal(Model.dueLabel(mk("2026-11-04"), TODAY), "amanhã")
  assert.equal(Model.dueLabel(mk("2026-11-02"), TODAY), "ontem")
  assert.equal(Model.dueLabel(mk("2026-11-06"), TODAY), "sex")
  assert.equal(Model.dueLabel(mk("2026-11-20"), TODAY), "20/11")
  assert.equal(Model.dueLabel(mk("2026-11-03", "15:00"), TODAY), "hoje 15:00")
})

test("rows ordena por seção e só mostra subpassos quando expandida", () => {
  const s = state([
    { id: "t1", title: "Sem data", createdAt: "1" },
    { id: "t2", title: "Hoje", due: TODAY, createdAt: "2", subtasks: [{ title: "a" }, { title: "b", done: true }] },
    { id: "t3", title: "Atrasada", due: "2026-11-01", createdAt: "3" },
    { id: "t4", title: "Feita", due: TODAY, createdAt: "4", completedAt: "2026-11-03T08:00:00" },
  ])
  const collapsed = Model.rows(s, { todayKey: TODAY })
  assert.deepEqual(collapsed.map(r => r.rowId), ["t3", "t2", "t1", "done"])
  assert.equal(collapsed[1].subDone, 1)
  assert.equal(collapsed[1].subTotal, 2)
  assert.equal(collapsed[1].hasSubs, true)
  assert.equal(collapsed[3].kind, "doneToggle")
  assert.equal(collapsed[3].subTotal, 1)

  const expanded = Model.rows(s, { todayKey: TODAY, expanded: { t2: true }, showCompleted: true })
  assert.deepEqual(expanded.map(r => r.rowId), ["t3", "t2", "t2.1", "t2.2", "t1", "done", "t4"])
  assert.equal(expanded[2].kind, "sub")
  assert.equal(expanded[2].depth, 1)
  assert.equal(expanded[3].done, true)
})

test("toda linha tem as mesmas chaves, como o ListModel exige", () => {
  const s = state([
    { id: "t1", title: "A", due: TODAY, subtasks: [{ title: "x" }] },
    { id: "t2", title: "B", completedAt: "2026-11-03T08:00:00" },
  ])
  const rows = Model.rows(s, { todayKey: TODAY, expanded: { t1: true }, showCompleted: true })
  const keys = Object.keys(rows[0]).sort().join(",")
  for (const row of rows) assert.equal(Object.keys(row).sort().join(","), keys)
})

test("counts conta abertas, de hoje e atrasadas", () => {
  const s = state([
    { id: "a", title: "a", due: "2026-11-01" },
    { id: "b", title: "b", due: TODAY },
    { id: "c", title: "c" },
    { id: "d", title: "d", due: TODAY, completedAt: "2026-11-03T08:00:00" },
  ])
  assert.deepEqual(Model.counts(s, TODAY), { open: 3, today: 1, overdue: 1, due: 2 })
})

test("eventRows agrupa por dia, dia todo primeiro, e preenche dias vazios", () => {
  const s = state([], [
    { id: "e1", title: "Tarde", start: "2026-11-03T15:00:00-03:00", end: "2026-11-03T16:00:00-03:00" },
    { id: "e2", title: "Aniversário", start: "2026-11-03", end: "2026-11-04", allDay: true },
    { id: "e3", title: "Viagem", start: "2026-11-05", end: "2026-11-07", allDay: true },
  ])
  const now = new Date(2026, 10, 3, 12, 0)
  const rows = Model.eventRows(s, { todayKey: TODAY, days: 5, now })
  const byDay = {}
  for (const r of rows) (byDay[r.sectionKey] = byDay[r.sectionKey] || []).push(r.rowId)
  assert.deepEqual(byDay["2026-11-03"], ["e2", "e1"])
  assert.deepEqual(byDay["2026-11-04"], ["empty:2026-11-04"])
  assert.deepEqual(byDay["2026-11-05"], ["e3"])
  assert.deepEqual(byDay["2026-11-06"], ["e3"])
  assert.deepEqual(byDay["2026-11-07"], ["empty:2026-11-07"])
  assert.equal(rows[0].timeLabel, "dia todo")
  assert.equal(rows[1].past, false)
})

test("dayLabel nomeia hoje, amanhã e o resto em maiúsculas", () => {
  assert.equal(Model.dayLabel("2026-11-03", TODAY), "HOJE · ter 3 nov")
  assert.equal(Model.dayLabel("2026-11-04", TODAY), "AMANHÃ · qua 4 nov")
  assert.equal(Model.dayLabel("2026-11-06", TODAY), "SEX 6 NOV")
})

test("barLabel prefere o evento iminente, senão o número de tarefas urgentes", () => {
  const now = new Date(2026, 10, 3, 14, 30)
  const withEvent = state([{ id: "a", title: "a", due: TODAY }], [
    { id: "e1", title: "Dentista", start: "2026-11-03T15:00:00", end: "2026-11-03T16:00:00" },
  ])
  assert.equal(Model.barLabel(withEvent, now), "15:00 Dentista")
  const onlyTasks = state([{ id: "a", title: "a", due: TODAY }, { id: "b", title: "b", due: "2026-11-01" }])
  assert.equal(Model.barLabel(onlyTasks, now), "2")
  assert.equal(Model.barLabel(state([]), now), "")
})

test("syncLabel descreve o estado da sincronização", () => {
  assert.equal(Model.syncLabel({ status: "none", lastOkAt: "" }), "sem sync")
  assert.equal(Model.syncLabel({ status: "error", lastOkAt: "2026-11-03T12:04:00" }), "erro de sync")
  assert.equal(Model.syncLabel({ status: "ok", lastOkAt: "2026-11-03T12:04:00" }), "sync 12:04")
})
