"""As operações da Agenda, sem interface nenhuma.

A CLI (bin/agenda) e a ponte de mensagens (agenda_bridge) chamam estas
funções. Cada uma pega a trava do state.json, muda o que tem de mudar e
devolve o que mudou. Erros de uso viram OpsError com uma mensagem em
português, que a CLI imprime e o bot responde.
"""

from __future__ import annotations

import re
import secrets
import unicodedata
from datetime import date, datetime, timedelta

import agenda_google as google
import agenda_store as store

ID_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
ID_LENGTH = 4
DEFAULT_EVENT_MINUTES = 60


class OpsError(Exception):
    """Pedido que não dá para atender: id inexistente, texto vazio, prazo que não entendi."""


# ---------------------------------------------------------------------------
# Identificadores
# ---------------------------------------------------------------------------


def existing_ids(state: dict) -> set[str]:
    ids = set()
    for bucket in ("tasks", "trash"):
        for task in state[bucket]:
            ids.add(task.get("id", ""))
    for event in state["events"]:
        ids.add(event.get("id", ""))
    return ids


def new_id(state: dict) -> str:
    """Quatro caracteres base36 começando por letra: curto para digitar numa mensagem."""
    taken = existing_ids(state)
    while True:
        candidate = "".join(secrets.choice(ID_ALPHABET) for _ in range(ID_LENGTH))
        if candidate not in taken and candidate[0].isalpha():
            return candidate


def find_task(state: dict, task_id: str) -> dict:
    for task in state["tasks"]:
        if task.get("id") == task_id:
            return task
    raise OpsError(f"tarefa '{task_id}' não existe")


def find_sub(state: dict, sub_id: str) -> tuple[dict, dict]:
    task_id, _, _ = sub_id.partition(".")
    task = find_task(state, task_id)
    for sub in task.get("subtasks", []):
        if sub.get("id") == sub_id:
            return task, sub
    raise OpsError(f"subpasso '{sub_id}' não existe")


def next_sub_id(task: dict) -> str:
    used = {sub.get("id", "") for sub in task.get("subtasks", [])}
    n = 1
    while f"{task['id']}.{n}" in used:
        n += 1
    return f"{task['id']}.{n}"


# ---------------------------------------------------------------------------
# Interpretação de texto em português
# ---------------------------------------------------------------------------

# Python conta a semana a partir da segunda (0) até o domingo (6).
WEEKDAYS = {
    "segunda": 0, "seg": 0, "segunda-feira": 0,
    "terca": 1, "ter": 1, "terca-feira": 1,
    "quarta": 2, "qua": 2, "quarta-feira": 2,
    "quinta": 3, "qui": 3, "quinta-feira": 3,
    "sexta": 4, "sex": 4, "sexta-feira": 4,
    "sabado": 5, "sab": 5,
    "domingo": 6, "dom": 6,
}
WEEKDAY_NAMES = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
CONNECTORS_BEFORE_DAY = {"na", "no", "nesta", "neste", "nessa", "nesse", "proxima", "proximo", "em"}
CONNECTORS_BEFORE_TIME = {"as", "a", "das"}

TIME_RE = re.compile(r"^(\d{1,2})(?:h|:)(\d{2})?$")
RANGE_RE = re.compile(r"^(\d{1,2})(?:h|:)?(\d{2})?-(\d{1,2})(?:h|:)?(\d{2})?$")
DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$")


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def clean_token(raw: str) -> str:
    return strip_accents(raw.lower()).strip(",.;")


def valid_time(hour: str, minute: str | None) -> str | None:
    h = int(hour)
    m = int(minute) if minute else 0
    if 0 <= h <= 23 and 0 <= m <= 59:
        return f"{h:02d}:{m:02d}"
    return None


def resolve_day_of_month(day: int, today: date) -> date | None:
    """'dia 12' é o dia 12 deste mês, ou do próximo se já passou."""
    for months_ahead in (0, 1):
        year = today.year + (today.month - 1 + months_ahead) // 12
        month = (today.month - 1 + months_ahead) % 12 + 1
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if candidate >= today:
            return candidate
    return None


def resolve_slash_date(match: re.Match, today: date) -> date | None:
    day, month, year = int(match.group(1)), int(match.group(2)), match.group(3)
    try:
        if year:
            y = int(year)
            if y < 100:
                y += 2000
            return date(y, month, day)
        candidate = date(today.year, month, day)
        if candidate < today:
            candidate = date(today.year + 1, month, day)
        return candidate
    except ValueError:
        return None


def parse_text(text: str, today: date | None = None) -> dict:
    """Separa o título das pistas de data e hora.

    "pagar luz amanhã"        -> título "pagar luz", prazo amanhã
    "dentista qui 15h"        -> título "dentista", quinta, 15:00
    "dentista qui 15h-16h30"  -> idem, com fim 16:30
    "relatório sex !"         -> prioridade alta
    """
    today = today or date.today()
    tokens = text.split()
    result = {"title": "", "due": None, "time": None, "endTime": None, "priority": 0}
    keep: list[str] = []
    i = 0
    while i < len(tokens):
        raw = tokens[i]
        tok = clean_token(raw)
        nxt = clean_token(tokens[i + 1]) if i + 1 < len(tokens) else ""

        if tok == "!":
            result["priority"] = 1
            i += 1
            continue
        if tok.endswith("!") and len(tok) > 1:
            result["priority"] = 1
            tok = tok[:-1]
            raw = raw.rstrip("!")

        # Conectivos só somem quando o que vem depois é mesmo uma data ou hora.
        if tok in CONNECTORS_BEFORE_DAY and (nxt in WEEKDAYS or nxt in ("hoje", "amanha") or DATE_RE.match(nxt)):
            i += 1
            continue
        if tok in CONNECTORS_BEFORE_TIME and (TIME_RE.match(nxt) or RANGE_RE.match(nxt)):
            i += 1
            continue

        if tok == "hoje":
            result["due"] = today
        elif tok == "amanha":
            result["due"] = today + timedelta(days=1)
        elif tok == "depois" and nxt == "de" and i + 2 < len(tokens) and clean_token(tokens[i + 2]) == "amanha":
            result["due"] = today + timedelta(days=2)
            i += 2
        elif tok in WEEKDAYS:
            delta = (WEEKDAYS[tok] - today.weekday()) % 7
            result["due"] = today + timedelta(days=delta)
        elif tok == "dia" and nxt.isdigit() and 1 <= int(nxt) <= 31:
            resolved = resolve_day_of_month(int(nxt), today)
            if resolved:
                result["due"] = resolved
                i += 1
            else:
                keep.append(raw)
        elif DATE_RE.match(tok):
            resolved = resolve_slash_date(DATE_RE.match(tok), today)
            if resolved:
                result["due"] = resolved
            else:
                keep.append(raw)
        elif RANGE_RE.match(tok):
            m = RANGE_RE.match(tok)
            start = valid_time(m.group(1), m.group(2))
            end = valid_time(m.group(3), m.group(4))
            if start and end:
                result["time"], result["endTime"] = start, end
            else:
                keep.append(raw)
        elif TIME_RE.match(tok):
            m = TIME_RE.match(tok)
            parsed = valid_time(m.group(1), m.group(2))
            if parsed:
                result["time"] = parsed
            else:
                keep.append(raw)
        else:
            keep.append(raw)
        i += 1

    result["title"] = " ".join(keep).strip(" ,.;")
    return result


def parse_due(value: str, today: date | None = None) -> date:
    """Aceita 'YYYY-MM-DD' ou a mesma linguagem do texto livre; sem data, OpsError."""
    today = today or date.today()
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    due = parse_text(value, today)["due"]
    if due is None:
        raise OpsError(f"não entendi o prazo '{value}'")
    return due


# ---------------------------------------------------------------------------
# Rótulos em português
# ---------------------------------------------------------------------------


def due_label(due: str, due_time: str = "", today: date | None = None) -> str:
    """'hoje', 'amanhã', 'sex', '12/11', como no painel."""
    if not due:
        return ""
    today = today or date.today()
    day = date.fromisoformat(due)
    diff = (day - today).days
    if diff == 0:
        label = "hoje"
    elif diff == 1:
        label = "amanhã"
    elif diff == -1:
        label = "ontem"
    elif 1 < diff < 7:
        label = WEEKDAY_NAMES[day.weekday()]
    else:
        label = day.strftime("%d/%m")
    return f"{label} {due_time}" if due_time else label


def event_label(event: dict) -> str:
    """'qui 05/11 15:00–16:00' ou 'qui 05/11, dia todo'."""
    start = str(event.get("start", ""))
    try:
        if event.get("allDay"):
            day = date.fromisoformat(start[:10])
            return f"{WEEKDAY_NAMES[day.weekday()]} {day.strftime('%d/%m')}, dia todo"
        begin = datetime.fromisoformat(start)
        label = f"{WEEKDAY_NAMES[begin.weekday()]} {begin.strftime('%d/%m %H:%M')}"
        if event.get("end"):
            label += "–" + datetime.fromisoformat(str(event["end"])).strftime("%H:%M")
        return label
    except ValueError:
        return start


def describe_task(task: dict) -> str:
    bits = [task["id"], task["title"]]
    if task.get("due"):
        bits.append(task["due"] + (" " + task["dueTime"] if task.get("dueTime") else ""))
    if task.get("priority"):
        bits.append("!")
    return "  ".join(bits)


SECTION_TITLES = [("overdue", "Atrasadas"), ("today", "Hoje"), ("soon", "Em breve"), ("nodate", "Sem data"), ("done", "Concluídas")]


def classify(task: dict, today: date) -> str:
    if task.get("completedAt"):
        return "done"
    if not task.get("due"):
        return "nodate"
    diff = (date.fromisoformat(task["due"]) - today).days
    if diff < 0:
        return "overdue"
    if diff == 0:
        return "today"
    return "soon"


def task_sort_key(task: dict):
    return (task.get("due") or "9999", task.get("dueTime") or "99", -int(task.get("priority") or 0), task.get("createdAt", ""))


def sections(state: dict, today: date | None = None, include_done: bool = False) -> list[tuple[str, list[dict]]]:
    """[(título da seção, tarefas ordenadas)], só com seções que têm algo."""
    today = today or date.today()
    buckets: dict[str, list[dict]] = {key: [] for key, _ in SECTION_TITLES}
    for task in state["tasks"]:
        buckets[classify(task, today)].append(task)
    out = []
    for key, title in SECTION_TITLES:
        if not buckets[key] or (key == "done" and not include_done):
            continue
        out.append((title, sorted(buckets[key], key=task_sort_key)))
    return out


# ---------------------------------------------------------------------------
# Tarefas
# ---------------------------------------------------------------------------


def make_task(state: dict, title: str, due: date | None, due_time: str | None, priority: int, subs: list[str]) -> dict:
    task = {
        "id": new_id(state),
        "title": title,
        "due": due.isoformat() if due else "",
        "dueTime": due_time or "",
        "priority": priority,
        "createdAt": store.iso(store.now_local()),
        "completedAt": "",
        "subtasks": [],
    }
    for sub_title in subs:
        sub_title = sub_title.strip()
        if sub_title:
            task["subtasks"].append({"id": next_sub_id(task), "title": sub_title, "done": False})
    return task


def add_task(text: str, due: str | None = None, subs: list[str] | None = None, priority: bool | None = None) -> dict:
    parsed = parse_text(text)
    if parsed["title"] == "":
        raise OpsError("a tarefa precisa de um título")
    when = parse_due(due) if due else parsed["due"]
    level = 1 if priority else (parsed["priority"] if priority is None else 0)
    with store.locked_state() as state:
        task = make_task(state, parsed["title"], when, parsed["time"], level, list(subs or []))
        state["tasks"].append(task)
    return task


def complete_task(task_id: str) -> dict:
    with store.locked_state() as state:
        task = find_task(state, task_id)
        task["completedAt"] = store.iso(store.now_local())
        for sub in task.get("subtasks", []):
            sub["done"] = True
    return task


def reopen_task(task_id: str) -> dict:
    with store.locked_state() as state:
        task = find_task(state, task_id)
        task["completedAt"] = ""
    return task


def delete_task(task_id: str) -> dict:
    """Vai para a lixeira; restore_task traz de volta por sete dias."""
    with store.locked_state() as state:
        task = find_task(state, task_id)
        state["tasks"] = [t for t in state["tasks"] if t is not task]
        task["deletedAt"] = store.iso(store.now_local())
        state["trash"].append(task)
    return task


def restore_task(task_id: str) -> dict:
    with store.locked_state() as state:
        for task in state["trash"]:
            if task.get("id") == task_id:
                state["trash"].remove(task)
                task.pop("deletedAt", None)
                state["tasks"].append(task)
                return task
        raise OpsError(f"'{task_id}' não está na lixeira")


def snooze_task(task_id: str, days: int = 1) -> dict:
    with store.locked_state() as state:
        task = find_task(state, task_id)
        base = date.fromisoformat(task["due"]) if task.get("due") else date.today()
        if base < date.today():
            base = date.today()
        task["due"] = (base + timedelta(days=days)).isoformat()
    return task


def edit_task(task_id: str, title: str | None = None, due: str | None = None, no_due: bool = False, priority: int | None = None) -> dict:
    with store.locked_state() as state:
        task = find_task(state, task_id)
        if title:
            task["title"] = title.strip()
        if no_due:
            task["due"], task["dueTime"] = "", ""
        elif due:
            parsed = parse_text(due)
            task["due"] = (parsed["due"] or parse_due(due)).isoformat()
            if parsed["time"]:
                task["dueTime"] = parsed["time"]
        if priority is not None:
            task["priority"] = 1 if priority else 0
    return task


def add_subtask(task_id: str, text: str) -> tuple[dict, dict]:
    title = text.strip()
    if not title:
        raise OpsError("o subpasso precisa de um título")
    with store.locked_state() as state:
        task = find_task(state, task_id)
        sub = {"id": next_sub_id(task), "title": title, "done": False}
        task.setdefault("subtasks", []).append(sub)
    return task, sub


def set_subtask(sub_id: str, done: bool) -> tuple[dict, dict]:
    with store.locked_state() as state:
        task, sub = find_sub(state, sub_id)
        sub["done"] = done
    return task, sub


def remove_subtask(sub_id: str) -> tuple[dict, dict]:
    with store.locked_state() as state:
        task, sub = find_sub(state, sub_id)
        task["subtasks"] = [s for s in task["subtasks"] if s is not sub]
    return task, sub


# ---------------------------------------------------------------------------
# Eventos: no Google quando configurado, locais quando não
# ---------------------------------------------------------------------------


def local_event(state: dict, title: str, day: date, start_time: str | None, end_time: str | None) -> dict:
    event = {
        "id": "l:" + new_id(state),
        "calendar": "local",
        "calendarId": "",
        "color": "",
        "title": title,
        "location": "",
        "url": "",
        "description": "",
    }
    body = google.event_body(title, day, start_time, end_time, store.now_local().tzinfo, DEFAULT_EVENT_MINUTES)
    if "dateTime" in body["start"]:
        event.update({"allDay": False, "start": body["start"]["dateTime"], "end": body["end"]["dateTime"]})
    else:
        event.update({"allDay": True, "start": body["start"]["date"], "end": body["end"]["date"]})
    return event


def add_event(text: str, local: bool = False) -> tuple[dict, str]:
    """Devolve (evento, origem), com origem 'google' ou 'local'."""
    parsed = parse_text(text)
    if parsed["title"] == "":
        raise OpsError("o evento precisa de um título")
    day = parsed["due"] or date.today()
    if google.is_configured() and not local:
        config = google.load_config()
        calendar_id = config["google"]["write_calendar"]
        api = google.connect()
        body = google.event_body(parsed["title"], day, parsed["time"], parsed["endTime"], store.now_local().tzinfo, DEFAULT_EVENT_MINUTES)
        created = api.insert_event(calendar_id, body)
        meta = next((c for c in api.calendar_list() if c.get("id") == calendar_id or (calendar_id == "primary" and c.get("primary"))), {})
        event = google.map_event(created, dict(meta, id=calendar_id))
        if event is None:
            raise OpsError("o Google criou o evento mas devolveu algo que não entendi")
        with store.locked_state() as state:
            state["events"] = [e for e in state["events"] if e.get("id") != event["id"]] + [event]
        return event, "google"
    with store.locked_state() as state:
        event = local_event(state, parsed["title"], day, parsed["time"], parsed["endTime"])
        state["events"].append(event)
    return event, "local"


def remove_event(event_id: str) -> dict:
    with store.locked_state() as state:
        event = next((e for e in state["events"] if e.get("id") == event_id), None)
        if event is None:
            raise OpsError(f"evento '{event_id}' não existe")
        if event_id.startswith("g:"):
            google.connect().delete_event(event.get("calendarId") or "primary", event_id[2:])
        state["events"] = [e for e in state["events"] if e is not event]
    return event


def upcoming_events(state: dict, days: int = 7, today: date | None = None) -> list[dict]:
    today = today or date.today()
    limit = (today + timedelta(days=days)).isoformat()
    picked = [e for e in state["events"] if today.isoformat() <= str(e.get("start", ""))[:10] < limit]
    return sorted(picked, key=lambda e: (str(e.get("start", ""))[:10], not e.get("allDay"), str(e.get("start", ""))))
