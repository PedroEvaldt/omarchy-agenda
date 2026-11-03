"""A ponte de mensagens, sem canal.

Recebe um texto como você mandaria do celular e devolve uma resposta com,
às vezes, botões. Não sabe o que é Telegram: quem sabe é agenda_telegram,
que só traduz mensagens e cliques para cá e respostas para lá. Trocar o
canal no futuro é escrever outro tradutor.

Gramática:
    t: texto            tarefa, mesmo que tenha hora
    e: texto            evento, mesmo que não tenha hora
    texto               com hora vira evento; sem hora vira tarefa
    feito 7k2a          conclui (botão Reabrir)
    adiar 7k2a [dias]   empurra o prazo
    sub 7k2a texto      subpasso
    apagar 7k2a         tarefa para a lixeira, ou evento fora
    restaurar 7k2a      traz da lixeira
    lista | hoje | agenda | ajuda
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

import agenda_google as google
import agenda_ops as ops
import agenda_store as store


@dataclass
class Reply:
    text: str
    # (rótulo do botão, dado que volta em handle_callback)
    buttons: list[tuple[str, str]] = field(default_factory=list)


HELP = """Mande o que quer lembrar:
• pagar luz amanhã → tarefa
• dentista qui 15h → evento
• t: ou e: na frente força tarefa ou evento
• relatório sex ! → prioridade

Comandos:
feito 7k2a · adiar 7k2a 2 · sub 7k2a texto
apagar 7k2a · restaurar 7k2a
lista · hoje · agenda · ajuda"""

COMMANDS = [
    (re.compile(r"^(?:feito|ok|concluir|pronto)\s+(\S+)$"), "done"),
    (re.compile(r"^(?:adiar)\s+(\S+)(?:\s+(\d+))?$"), "snooze"),
    (re.compile(r"^(?:sub|passo)\s+(\S+)\s+(.+)$"), "sub"),
    (re.compile(r"^(?:apagar|excluir|remover|rm)\s+(\S+)$"), "delete"),
    (re.compile(r"^(?:restaurar|desfazer)\s+(\S+)$"), "restore"),
]
LIST_WORDS = {"lista", "tarefas", "l"}
TODAY_WORDS = {"hoje", "h"}
AGENDA_WORDS = {"agenda", "eventos", "semana"}
HELP_WORDS = {"/start", "/help", "ajuda", "help", "?"}


def _task_line(task: dict, today: date) -> str:
    box = "☑" if task.get("completedAt") else "☐"
    due = ops.due_label(task.get("due", ""), task.get("dueTime", ""), today)
    prio = " !" if task.get("priority") else ""
    subs = task.get("subtasks") or []
    progress = f" ({sum(1 for s in subs if s.get('done'))}/{len(subs)})" if subs else ""
    return f"{box} {task['id']} {task['title']}{progress}{prio}" + (f" · {due}" if due else "")


def created_task_reply(task: dict, today: date | None = None) -> Reply:
    today = today or date.today()
    due = ops.due_label(task["due"], task["dueTime"], today)
    text = f"✓ Tarefa {task['id']}: {task['title']}" + (f" · {due}" if due else "") + (" !" if task.get("priority") else "")
    return Reply(text, [("Desfazer", f"undo:task:{task['id']}")])


def created_event_reply(event: dict, origin: str) -> Reply:
    where = f" (Google: {event.get('calendar')})" if origin == "google" else " (local)"
    text = f"✓ Evento: {event['title']} · {ops.event_label(event)}{where}"
    return Reply(text, [("Desfazer", f"undo:event:{event['id']}")])


def list_reply(today: date | None = None) -> Reply:
    today = today or date.today()
    state = store.read_state()
    blocks = []
    for title, tasks in ops.sections(state, today):
        blocks.append(title.upper() + "\n" + "\n".join(_task_line(t, today) for t in tasks))
    return Reply("\n\n".join(blocks) if blocks else "Nada por fazer.")


def today_reply(today: date | None = None) -> Reply:
    today = today or date.today()
    state = store.read_state()
    key = today.isoformat()
    events = [e for e in ops.upcoming_events(state, 1, today)]
    tasks = [t for t in state["tasks"] if not t.get("completedAt") and t.get("due") and t["due"] <= key]
    lines = [f"{'dia todo' if e.get('allDay') else ops.event_label(e).split(' ', 2)[-1]}  {e['title']}" for e in events]
    lines += [_task_line(t, today) for t in sorted(tasks, key=ops.task_sort_key)]
    head = f"Hoje: {len(events)} evento{'s' if len(events) != 1 else ''}, {len(tasks)} tarefa{'s' if len(tasks) != 1 else ''}"
    return Reply(head + ("\n" + "\n".join(lines) if lines else "\nDia livre."))


def agenda_reply(today: date | None = None, days: int = 7) -> Reply:
    today = today or date.today()
    state = store.read_state()
    events = ops.upcoming_events(state, days, today)
    if not events:
        return Reply(f"Nada marcado nos próximos {days} dias.")
    lines = [f"{ops.event_label(e)}  {e['title']}" + (f" · {e['location']}" if e.get("location") else "") for e in events]
    return Reply("\n".join(lines))


def handle_text(text: str, today: date | None = None) -> Reply:
    """Uma mensagem entra, uma resposta sai. Nunca levanta exceção de uso."""
    today = today or date.today()
    raw = text.strip()
    if raw == "":
        return Reply("Mande um texto. 'ajuda' mostra o que eu entendo.")
    low = ops.strip_accents(raw.lower())
    try:
        if low in HELP_WORDS:
            return Reply(HELP)
        if low in LIST_WORDS:
            return list_reply(today)
        if low in TODAY_WORDS:
            return today_reply(today)
        if low in AGENDA_WORDS:
            return agenda_reply(today)
        if low.startswith("t:"):
            return created_task_reply(ops.add_task(raw[2:]), today)
        if low.startswith("e:"):
            event, origin = ops.add_event(raw[2:])
            return created_event_reply(event, origin)
        for pattern, name in COMMANDS:
            match = pattern.match(low)
            if not match:
                continue
            ident = match.group(1)
            if name == "done":
                task = ops.complete_task(ident)
                return Reply(f"✓ Concluída: {task['title']}", [("Reabrir", f"reopen:{task['id']}")])
            if name == "snooze":
                days = int(match.group(2) or 1)
                task = ops.snooze_task(ident, days)
                return Reply(f"↻ {task['title']} · {ops.due_label(task['due'], task.get('dueTime', ''), today)}")
            if name == "sub":
                # O texto do subpasso vem do original, com acentos e maiúsculas.
                body = raw.split(None, 2)[2]
                task, sub = ops.add_subtask(ident, body)
                return Reply(f"✓ Subpasso {sub['id']} em {task['title']}: {sub['title']}")
            if name == "delete":
                if ident.startswith(("g:", "l:")):
                    event = ops.remove_event(ident)
                    return Reply(f"✗ Evento apagado: {event['title']}")
                task = ops.delete_task(ident)
                return Reply(f"✗ Apagada: {task['title']}", [("Restaurar", f"restore:{task['id']}")])
            if name == "restore":
                task = ops.restore_task(ident)
                return Reply(f"↩ Restaurada: {task['title']}")
        # Sem comando nem prefixo: a hora decide.
        parsed = ops.parse_text(raw, today)
        if parsed["time"]:
            event, origin = ops.add_event(raw)
            return created_event_reply(event, origin)
        return created_task_reply(ops.add_task(raw), today)
    except (ops.OpsError, google.GoogleError, store.StoreError) as error:
        return Reply(f"⚠ {error}")


def handle_callback(data: str) -> Reply:
    """Clique num botão. O dado é o que created_*_reply colocou nele."""
    try:
        kind, _, ident = data.partition(":")
        if kind == "undo":
            what, _, ident = ident.partition(":")
            if what == "task":
                task = ops.delete_task(ident)
                return Reply(f"✗ Desfeito: {task['title']}")
            if what == "event":
                event = ops.remove_event(ident)
                return Reply(f"✗ Desfeito: {event['title']}")
        if kind == "reopen":
            task = ops.reopen_task(ident)
            return Reply(f"↩ Reaberta: {task['title']}")
        if kind == "restore":
            task = ops.restore_task(ident)
            return Reply(f"↩ Restaurada: {task['title']}")
        return Reply("⚠ Botão que não reconheço.")
    except (ops.OpsError, google.GoogleError, store.StoreError) as error:
        return Reply(f"⚠ {error}")
