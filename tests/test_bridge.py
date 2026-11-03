"""Testes da ponte de mensagens: texto entra, resposta e botões saem, estado muda."""

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import agenda_bridge as bridge  # noqa: E402
import agenda_ops as ops  # noqa: E402
import agenda_store as store  # noqa: E402

TODAY = date(2026, 11, 3)  # terça


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENDA_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("AGENDA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("AGENDA_NO_KEYRING", "1")
    monkeypatch.setenv("AGENDA_NO_NOTIFY", "1")


def tasks():
    return store.read_state()["tasks"]


def test_texto_sem_hora_vira_tarefa_com_botao_de_desfazer():
    reply = bridge.handle_text("pagar luz amanhã", TODAY)
    assert reply.text.startswith("✓ Tarefa ")
    assert reply.text.endswith(": pagar luz · amanhã")
    assert len(tasks()) == 1
    task_id = tasks()[0]["id"]
    assert reply.buttons == [("Desfazer", f"undo:task:{task_id}")]

    undo = bridge.handle_callback(reply.buttons[0][1])
    assert undo.text == "✗ Desfeito: pagar luz"
    assert tasks() == []
    assert store.read_state()["trash"][0]["id"] == task_id


def test_texto_com_hora_vira_evento_local():
    reply = bridge.handle_text("dentista qui 15h", TODAY)
    assert reply.text.startswith("✓ Evento: dentista · qui 05/11 15:00–16:00 (local)")
    events = store.read_state()["events"]
    assert len(events) == 1 and events[0]["id"].startswith("l:")
    assert reply.buttons == [("Desfazer", f"undo:event:{events[0]['id']}")]
    assert bridge.handle_callback(reply.buttons[0][1]).text == "✗ Desfeito: dentista"
    assert store.read_state()["events"] == []


def test_prefixos_forcam_o_tipo():
    bridge.handle_text("t: reunião 15h", TODAY)
    bridge.handle_text("e: feriado", TODAY)
    state = store.read_state()
    assert [t["title"] for t in state["tasks"]] == ["reunião"]
    assert state["tasks"][0]["dueTime"] == "15:00"
    assert [e["title"] for e in state["events"]] == ["feriado"]
    assert state["events"][0]["allDay"] is True


def test_feito_adiar_sub_apagar_restaurar():
    task_id = ops.add_task("relatório sex")["id"]

    done = bridge.handle_text(f"feito {task_id}", TODAY)
    assert done.text == "✓ Concluída: relatório"
    assert done.buttons == [("Reabrir", f"reopen:{task_id}")]
    assert tasks()[0]["completedAt"] != ""
    assert bridge.handle_callback(f"reopen:{task_id}").text == "↩ Reaberta: relatório"
    assert tasks()[0]["completedAt"] == ""

    assert bridge.handle_text(f"adiar {task_id} 2", TODAY).text.startswith("↻ relatório · ")
    assert bridge.handle_text(f"sub {task_id} Revisar Gráficos", TODAY).text == f"✓ Subpasso {task_id}.1 em relatório: Revisar Gráficos"

    gone = bridge.handle_text(f"apagar {task_id}", TODAY)
    assert gone.text == "✗ Apagada: relatório"
    assert gone.buttons == [("Restaurar", f"restore:{task_id}")]
    assert tasks() == []
    assert bridge.handle_text(f"restaurar {task_id}", TODAY).text == "↩ Restaurada: relatório"
    assert tasks()[0]["id"] == task_id


def test_lista_hoje_agenda_e_ajuda():
    # As operações usam o dia de hoje de verdade, então o teste também usa.
    today = date.today()
    ops.add_task("atrasada", due=(today - timedelta(days=2)).isoformat())
    ops.add_task("de hoje", due=today.isoformat())
    ops.add_event("dentista hoje 15h")
    assert bridge.handle_text("ajuda", today).text == bridge.HELP
    listing = bridge.handle_text("lista", today).text
    assert "ATRASADAS" in listing and "HOJE" in listing and "☐" in listing
    hoje = bridge.handle_text("hoje", today).text
    assert hoje.startswith("Hoje: 1 evento, 2 tarefas")
    assert "15:00–16:00  dentista" in hoje
    assert "dentista" in bridge.handle_text("agenda", today).text
    assert bridge.handle_text("", today).text.startswith("Mande um texto")


def test_erros_viram_respostas_e_nao_excecoes():
    assert bridge.handle_text("feito zzzz", TODAY).text == "⚠ tarefa 'zzzz' não existe"
    assert bridge.handle_text("t: !", TODAY).text == "⚠ a tarefa precisa de um título"
    assert bridge.handle_callback("sei:la").text.startswith("⚠")
    assert bridge.handle_callback("undo:task:zzzz").text.startswith("⚠")
