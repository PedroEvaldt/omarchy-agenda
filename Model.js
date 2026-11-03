// Model.js — lógica pura do painel Agenda.
//
// Nada aqui depende de Qt ou Quickshell: é JavaScript comum, o que permite
// testar com `node --test tests/` sem abrir o shell. O QML importa este
// arquivo (`import "Model.js" as Model`) e chama as funções para transformar
// o state.json em linhas prontas para desenhar.
//
// Convenções:
// - Datas de prazo são strings "YYYY-MM-DD" no fuso local ("chave de dia").
// - Horas são "HH:MM".
// - Eventos com hora usam ISO 8601 completo; eventos de dia todo usam só a data.

var WEEKDAYS_SHORT = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"]
var MONTHS_SHORT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

// Ordem das seções da aba Tarefas. "done" é a seção recolhida no fim.
var SECTION_ORDER = ["overdue", "today", "soon", "nodate"]
var SECTION_LABELS = { overdue: "ATRASADAS", today: "HOJE", soon: "EM BREVE", nodate: "SEM DATA", done: "" }

function pad2(n) { return (n < 10 ? "0" : "") + n }

// "2026-11-03" a partir de um Date, no fuso local.
function dateKey(d) {
  return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate())
}

// Date local ao meio-dia a partir de "YYYY-MM-DD". Meio-dia, e não meia-noite,
// para que mudanças de horário de verão não empurrem o dia para o vizinho.
function dateFromKey(key) {
  var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(key || ""))
  if (!m) return null
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), 12)
}

function daysBetween(fromKey, toKey) {
  var a = dateFromKey(fromKey), b = dateFromKey(toKey)
  if (!a || !b) return 0
  return Math.round((b - a) / 86400000)
}

function addDays(key, n) {
  var d = dateFromKey(key)
  if (!d) return key
  d.setDate(d.getDate() + n)
  return dateKey(d)
}

// ---------------------------------------------------------------------------
// Estado
// ---------------------------------------------------------------------------

function emptyState() {
  return { tasks: [], events: [], trash: [], sync: { lastOkAt: "", status: "none", error: "" }, generatedAt: "" }
}

function normalizeSubtask(raw, taskId, index) {
  if (!raw || typeof raw.title !== "string") return null
  var title = raw.title.trim()
  if (title === "") return null
  return { id: String(raw.id || (taskId + "." + (index + 1))), title: title, done: raw.done === true }
}

function normalizeTask(raw) {
  if (!raw || typeof raw.title !== "string") return null
  var title = raw.title.trim()
  var id = String(raw.id || "")
  if (title === "" || id === "") return null
  var subs = []
  if (Array.isArray(raw.subtasks)) {
    for (var i = 0; i < raw.subtasks.length; i++) {
      var sub = normalizeSubtask(raw.subtasks[i], id, i)
      if (sub) subs.push(sub)
    }
  }
  return {
    id: id,
    title: title,
    due: typeof raw.due === "string" ? raw.due.slice(0, 10) : "",
    dueTime: typeof raw.dueTime === "string" ? raw.dueTime : "",
    priority: raw.priority === 1 || raw.priority === true ? 1 : 0,
    createdAt: String(raw.createdAt || ""),
    completedAt: typeof raw.completedAt === "string" ? raw.completedAt : "",
    subtasks: subs
  }
}

function normalizeEvent(raw) {
  if (!raw || typeof raw.title !== "string") return null
  var start = String(raw.start || "")
  if (start === "") return null
  return {
    id: String(raw.id || (start + "|" + raw.title)),
    calendar: String(raw.calendar || ""),
    color: String(raw.color || ""),
    title: raw.title.trim() || "(sem título)",
    start: start,
    end: String(raw.end || ""),
    allDay: raw.allDay === true || start.length === 10,
    location: String(raw.location || ""),
    url: String(raw.url || ""),
    description: String(raw.description || "")
  }
}

// Lê o texto do state.json e devolve um estado sempre bem formado. Arquivo
// vazio, inexistente ou corrompido vira um estado vazio em vez de um erro.
function parseState(raw) {
  var state = emptyState()
  var parsed = null
  try { parsed = JSON.parse(String(raw || "")) } catch (e) { return state }
  if (!parsed || typeof parsed !== "object") return state
  var i
  if (Array.isArray(parsed.tasks)) {
    for (i = 0; i < parsed.tasks.length; i++) {
      var task = normalizeTask(parsed.tasks[i])
      if (task) state.tasks.push(task)
    }
  }
  if (Array.isArray(parsed.events)) {
    for (i = 0; i < parsed.events.length; i++) {
      var event = normalizeEvent(parsed.events[i])
      if (event) state.events.push(event)
    }
  }
  if (parsed.sync && typeof parsed.sync === "object") {
    state.sync = {
      lastOkAt: String(parsed.sync.lastOkAt || ""),
      status: String(parsed.sync.status || "none"),
      error: String(parsed.sync.error || "")
    }
  }
  state.generatedAt = String(parsed.generatedAt || "")
  return state
}

// ---------------------------------------------------------------------------
// Tarefas
// ---------------------------------------------------------------------------

// Em qual seção a tarefa cai, dado o dia de hoje.
function classify(task, todayKey) {
  if (task.completedAt !== "") return "done"
  if (task.due === "") return "nodate"
  var diff = daysBetween(todayKey, task.due)
  if (diff < 0) return "overdue"
  if (diff === 0) return "today"
  return "soon"
}

// Com prazo antes de sem prazo; prazo mais próximo primeiro; depois a hora;
// depois prioridade; por fim a ordem de criação.
function compareTasks(a, b) {
  if (a.due !== b.due) {
    if (a.due === "") return 1
    if (b.due === "") return -1
    return a.due < b.due ? -1 : 1
  }
  if (a.dueTime !== b.dueTime) {
    if (a.dueTime === "") return 1
    if (b.dueTime === "") return -1
    return a.dueTime < b.dueTime ? -1 : 1
  }
  if (a.priority !== b.priority) return b.priority - a.priority
  if (a.createdAt !== b.createdAt) return a.createdAt < b.createdAt ? -1 : 1
  return 0
}

// Texto curto do prazo, à direita da linha: "hoje", "amanhã", "sex", "12/11".
function dueLabel(task, todayKey) {
  if (task.due === "") return ""
  var diff = daysBetween(todayKey, task.due)
  var d = dateFromKey(task.due)
  var label
  if (diff === 0) label = "hoje"
  else if (diff === 1) label = "amanhã"
  else if (diff === -1) label = "ontem"
  else if (diff > 1 && diff < 7) label = WEEKDAYS_SHORT[d.getDay()]
  else label = pad2(d.getDate()) + "/" + pad2(d.getMonth() + 1)
  if (task.dueTime !== "") label += " " + task.dueTime
  return label
}

function subProgress(task) {
  var done = 0
  for (var i = 0; i < task.subtasks.length; i++) if (task.subtasks[i].done) done++
  return { done: done, total: task.subtasks.length }
}

// Toda linha carrega as mesmas chaves, porque um ListModel do QML fixa os
// papéis (roles) na primeira inserção.
function taskRow(task, section, todayKey, expanded) {
  var progress = subProgress(task)
  return {
    kind: "task", rowId: task.id, taskId: task.id, title: task.title,
    done: task.completedAt !== "", dueLabel: dueLabel(task, todayKey),
    overdue: section === "overdue", hasSubs: progress.total > 0, expanded: expanded,
    subDone: progress.done, subTotal: progress.total, sectionKey: section,
    priority: task.priority, depth: 0
  }
}

function subRow(task, sub, section) {
  return {
    kind: "sub", rowId: sub.id, taskId: task.id, title: sub.title,
    done: sub.done, dueLabel: "", overdue: false, hasSubs: false, expanded: false,
    subDone: 0, subTotal: 0, sectionKey: section, priority: 0, depth: 1
  }
}

function doneToggleRow(count, expanded) {
  return {
    kind: "doneToggle", rowId: "done", taskId: "", title: "Concluídas",
    done: false, dueLabel: "", overdue: false, hasSubs: true, expanded: expanded,
    subDone: 0, subTotal: count, sectionKey: "done", priority: 0, depth: 0
  }
}

function pushTaskWithSubs(out, task, section, todayKey, expanded) {
  var isOpen = expanded[task.id] === true
  out.push(taskRow(task, section, todayKey, isOpen))
  if (!isOpen) return
  for (var i = 0; i < task.subtasks.length; i++) out.push(subRow(task, task.subtasks[i], section))
}

// A lista plana que a aba Tarefas desenha. Subpassos só entram quando a
// tarefa mãe está expandida; as concluídas só quando showCompleted é true.
function rows(state, opts) {
  opts = opts || {}
  var todayKey = opts.todayKey || dateKey(new Date())
  var expanded = opts.expanded || {}
  var buckets = { overdue: [], today: [], soon: [], nodate: [], done: [] }
  var i
  for (i = 0; i < state.tasks.length; i++) {
    var task = state.tasks[i]
    buckets[classify(task, todayKey)].push(task)
  }
  var out = []
  for (var s = 0; s < SECTION_ORDER.length; s++) {
    var section = SECTION_ORDER[s]
    var list = buckets[section].slice().sort(compareTasks)
    for (i = 0; i < list.length; i++) pushTaskWithSubs(out, list[i], section, todayKey, expanded)
  }
  var done = buckets.done.slice().sort(function(a, b) { return a.completedAt < b.completedAt ? 1 : a.completedAt > b.completedAt ? -1 : 0 })
  if (done.length > 0) {
    var show = opts.showCompleted === true
    out.push(doneToggleRow(done.length, show))
    if (show) for (i = 0; i < done.length; i++) pushTaskWithSubs(out, done[i], "done", todayKey, expanded)
  }
  return out
}

function sectionLabel(key) {
  return SECTION_LABELS[key] || ""
}

function counts(state, todayKey) {
  var open = 0, today = 0, overdue = 0
  for (var i = 0; i < state.tasks.length; i++) {
    var c = classify(state.tasks[i], todayKey)
    if (c === "done") continue
    open++
    if (c === "today") today++
    if (c === "overdue") overdue++
  }
  return { open: open, today: today, overdue: overdue, due: today + overdue }
}

// ---------------------------------------------------------------------------
// Eventos
// ---------------------------------------------------------------------------

function timeLabel(iso) {
  var d = new Date(iso)
  if (isNaN(d.getTime())) return ""
  return pad2(d.getHours()) + ":" + pad2(d.getMinutes())
}

// Em quais dias o evento aparece. Dia todo usa a convenção do Google: o fim
// é exclusivo, então um evento de 3 a 5 aparece nos dias 3 e 4.
function eventDays(ev) {
  if (ev.allDay) {
    var start = ev.start.slice(0, 10)
    var end = ev.end ? ev.end.slice(0, 10) : ""
    var days = [start]
    var guard = 0
    var k = addDays(start, 1)
    while (end !== "" && k < end && guard < 60) {
      days.push(k)
      k = addDays(k, 1)
      guard++
    }
    return days
  }
  var d = new Date(ev.start)
  if (isNaN(d.getTime())) return []
  return [dateKey(d)]
}

function eventRange(ev) {
  if (ev.allDay) return "dia todo"
  var s = timeLabel(ev.start)
  var e = ev.end ? timeLabel(ev.end) : ""
  return e !== "" ? s + "–" + e : s
}

function compareEvents(a, b) {
  if (a.allDay !== b.allDay) return a.allDay ? -1 : 1
  return a.start < b.start ? -1 : a.start > b.start ? 1 : 0
}

// Cabeçalho de cada dia na aba Agenda: "HOJE · ter 3 nov", "AMANHÃ · qua 4 nov", "QUI 5 NOV".
function dayLabel(key, todayKey) {
  var d = dateFromKey(key)
  if (!d) return String(key)
  var base = WEEKDAYS_SHORT[d.getDay()] + " " + d.getDate() + " " + MONTHS_SHORT[d.getMonth()]
  var diff = daysBetween(todayKey, key)
  if (diff === 0) return "HOJE · " + base
  if (diff === 1) return "AMANHÃ · " + base
  return base.toUpperCase()
}

function eventRows(state, opts) {
  opts = opts || {}
  var todayKey = opts.todayKey || dateKey(new Date())
  var days = opts.days || 7
  var now = opts.now || new Date()
  var byDay = {}
  var i, j
  for (i = 0; i < state.events.length; i++) {
    var ev = state.events[i]
    var keys = eventDays(ev)
    for (j = 0; j < keys.length; j++) {
      if (!byDay[keys[j]]) byDay[keys[j]] = []
      byDay[keys[j]].push(ev)
    }
  }
  var out = []
  for (i = 0; i < days; i++) {
    var key = addDays(todayKey, i)
    var list = (byDay[key] || []).slice().sort(compareEvents)
    if (list.length === 0) {
      out.push({ kind: "empty", rowId: "empty:" + key, title: "nada marcado", timeLabel: "", location: "", url: "", past: false, sectionKey: key, color: "" })
      continue
    }
    for (j = 0; j < list.length; j++) {
      var e = list[j]
      var endDate = e.end ? new Date(e.end) : null
      var past = !e.allDay && endDate !== null && !isNaN(endDate.getTime()) && endDate < now
      out.push({ kind: "event", rowId: e.id, title: e.title, timeLabel: eventRange(e), location: e.location, url: e.url, past: past, sectionKey: key, color: e.color })
    }
  }
  return out
}

// O próximo evento com hora que começa dentro da janela (ou começou há pouco).
function nextEvent(state, now, withinMinutes) {
  withinMinutes = withinMinutes || 60
  var best = null
  for (var i = 0; i < state.events.length; i++) {
    var ev = state.events[i]
    if (ev.allDay) continue
    var s = new Date(ev.start)
    if (isNaN(s.getTime())) continue
    var diff = (s - now) / 60000
    if (diff < -5 || diff > withinMinutes) continue
    if (!best || s < new Date(best.start)) best = ev
  }
  return best
}

// O que o widget da barra mostra ao lado do ícone.
function barLabel(state, now) {
  var ev = nextEvent(state, now)
  if (ev) return timeLabel(ev.start) + " " + ev.title
  var c = counts(state, dateKey(now))
  return c.due > 0 ? String(c.due) : ""
}

// Tooltip do widget: até três itens, tarefas urgentes e eventos de hoje.
function tooltip(state, now) {
  var todayKey = dateKey(now)
  var lines = []
  var i
  var urgent = state.tasks.filter(function(t) { var c = classify(t, todayKey); return c === "overdue" || c === "today" }).sort(compareTasks)
  for (i = 0; i < urgent.length && lines.length < 3; i++) lines.push("󰄱 " + urgent[i].title + (urgent[i].due !== "" ? " · " + dueLabel(urgent[i], todayKey) : ""))
  var todays = state.events.filter(function(e) { return eventDays(e).indexOf(todayKey) >= 0 }).sort(compareEvents)
  for (i = 0; i < todays.length && lines.length < 3; i++) lines.push("󰃭 " + eventRange(todays[i]) + " " + todays[i].title)
  return lines.length > 0 ? lines.join("\n") : "Agenda"
}

function syncLabel(sync) {
  if (!sync || sync.status === "none" || !sync.lastOkAt) return "sem sync"
  if (sync.status === "error") return "erro de sync"
  var d = new Date(sync.lastOkAt)
  if (isNaN(d.getTime())) return "sync"
  return "sync " + pad2(d.getHours()) + ":" + pad2(d.getMinutes())
}

if (typeof module !== "undefined") {
  module.exports = {
    dateKey: dateKey, dateFromKey: dateFromKey, daysBetween: daysBetween, addDays: addDays,
    emptyState: emptyState, parseState: parseState, classify: classify, compareTasks: compareTasks,
    dueLabel: dueLabel, rows: rows, sectionLabel: sectionLabel, counts: counts,
    timeLabel: timeLabel, eventDays: eventDays, eventRange: eventRange, dayLabel: dayLabel,
    eventRows: eventRows, nextEvent: nextEvent, barLabel: barLabel, tooltip: tooltip, syncLabel: syncLabel
  }
}
