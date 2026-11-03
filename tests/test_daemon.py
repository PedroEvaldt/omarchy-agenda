"""Testes do agendad: lembretes, resumo do dia e unidade do systemd. Sem laço e sem rede."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import agenda_daemon as daemon  # noqa: E402

TZ = timezone(timedelta(hours=-3))
NOW = datetime(2026, 11, 3, 14, 50, tzinfo=TZ)


def event(id_, start, end=None, all_day=False, **extra):
    data = {"id": id_, "title": id_, "start": start, "end": end or "", "allDay": all_day, "location": "", "url": ""}
    data.update(extra)
    return data


def test_due_reminders_respeita_janela_e_o_que_ja_foi_avisado():
    events = [
        event("em5", "2026-11-03T14:55:00-03:00"),
        event("em10", "2026-11-03T15:00:00-03:00"),
        event("em11", "2026-11-03T15:01:00-03:00"),
        event("agora", "2026-11-03T14:49:00-03:00"),
        event("passado", "2026-11-03T14:40:00-03:00"),
        event("diatodo", "2026-11-03", all_day=True),
        event("avisado", "2026-11-03T14:58:00-03:00"),
    ]
    due = daemon.due_reminders(events, NOW, 10, {"avisado": "x"})
    assert [e["id"] for e in due] == ["agora", "em5", "em10"]


def test_reminder_text():
    title, body = daemon.reminder_text(event("Dentista", "2026-11-03T15:00:00-03:00", "2026-11-03T16:00:00-03:00", location="Centro"), NOW)
    assert title == "Dentista em 10 min"
    assert body == "15:00–16:00 · Centro"
    title, _ = daemon.reminder_text(event("Agora", "2026-11-03T14:50:00-03:00"), NOW)
    assert title == "Agora agora"


def test_morning_summary_due():
    assert daemon.morning_summary_due("", NOW, "") is False
    assert daemon.morning_summary_due("08:00", NOW, "") is True
    assert daemon.morning_summary_due("08:00", NOW, "2026-11-03") is False
    assert daemon.morning_summary_due("16:00", NOW, "") is False
    assert daemon.morning_summary_due("errado", NOW, "") is False


def test_summary_text_conta_eventos_e_tarefas_de_hoje():
    state = {
        "tasks": [
            {"title": "Atrasada", "due": "2026-11-01", "completedAt": ""},
            {"title": "Hoje", "due": "2026-11-03", "completedAt": "", "dueTime": "15:00"},
            {"title": "Feita", "due": "2026-11-03", "completedAt": "2026-11-03T08:00:00"},
            {"title": "Amanhã", "due": "2026-11-04", "completedAt": ""},
        ],
        "events": [
            event("Dentista", "2026-11-03T15:00:00-03:00"),
            event("Aniversário", "2026-11-03", all_day=True),
            event("Outro dia", "2026-11-04T10:00:00-03:00"),
        ],
    }
    title, body = daemon.summary_text(state, NOW)
    assert title == "Hoje: 2 eventos, 2 tarefas"
    assert body.splitlines() == ["dia todo  Aniversário", "15:00  Dentista", "󰄱  Atrasada", "󰄱  Hoje"]
    assert daemon.summary_text({"tasks": [], "events": []}, NOW) == ("Hoje: 0 eventos, 0 tarefas", "Dia livre.")


def test_unit_text_aponta_para_o_executavel():
    text = daemon.unit_text("/home/x/.config/omarchy/plugins/pedro.agenda/bin/agenda")
    assert "ExecStart=/home/x/.config/omarchy/plugins/pedro.agenda/bin/agenda daemon" in text
    assert "WantedBy=default.target" in text
