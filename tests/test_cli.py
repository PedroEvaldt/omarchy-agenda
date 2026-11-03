"""Testes da CLI: `pytest tests/`. Usam um state.json temporário via AGENDA_STATE."""

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "bin" / "agenda"


def load_module():
    loader = importlib.machinery.SourceFileLoader("agenda_cli", str(CLI))
    spec = importlib.util.spec_from_loader("agenda_cli", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


agenda = load_module()
TODAY = date(2026, 11, 3)  # terça-feira


@pytest.fixture
def env(tmp_path, monkeypatch):
    state = tmp_path / "state.json"
    monkeypatch.setenv("AGENDA_STATE", str(state))
    monkeypatch.setenv("AGENDA_NO_NOTIFY", "1")
    return state


def run(*args):
    result = subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, env=os.environ.copy())
    return result


def read(state_file):
    return json.loads(state_file.read_text(encoding="utf-8"))


# ---- parse_text --------------------------------------------------------------

@pytest.mark.parametrize("text,title,due,time,end,prio", [
    ("comprar leite", "comprar leite", None, None, None, 0),
    ("pagar luz amanhã", "pagar luz", TODAY + timedelta(days=1), None, None, 0),
    ("pagar luz hoje", "pagar luz", TODAY, None, None, 0),
    ("depois de amanhã lavar o carro", "lavar o carro", TODAY + timedelta(days=2), None, None, 0),
    ("dentista qui 15h", "dentista", date(2026, 11, 5), "15:00", None, 0),
    ("dentista na quinta às 15h30", "dentista", date(2026, 11, 5), "15:30", None, 0),
    ("dentista qui 15h-16h30", "dentista", date(2026, 11, 5), "15:00", "16:30", 0),
    ("reunião ter 9:00", "reunião", TODAY, "09:00", None, 0),
    ("relatório sex !", "relatório", date(2026, 11, 6), None, None, 1),
    ("relatório sex!", "relatório", date(2026, 11, 6), None, None, 1),
    ("aniversário dia 12", "aniversário", date(2026, 11, 12), None, None, 0),
    ("aniversário dia 1", "aniversário", date(2026, 12, 1), None, None, 0),
    ("viagem 20/12", "viagem", date(2026, 12, 20), None, None, 0),
    ("viagem 05/01/27", "viagem", date(2027, 1, 5), None, None, 0),
    ("ir a padaria", "ir a padaria", None, None, None, 0),
])
def test_parse_text(text, title, due, time, end, prio):
    parsed = agenda.parse_text(text, TODAY)
    assert parsed["title"] == title
    assert parsed["due"] == due
    assert parsed["time"] == time
    assert parsed["endTime"] == end
    assert parsed["priority"] == prio


# ---- fluxo de tarefas --------------------------------------------------------

def test_add_done_undo_rm_restore(env):
    out = run("add", "pagar luz amanhã").stdout
    task_id = out.split()[0]
    state = read(env)
    assert len(state["tasks"]) == 1
    assert state["tasks"][0]["title"] == "pagar luz"
    assert state["tasks"][0]["due"] == (date.today() + timedelta(days=1)).isoformat()
    assert len(task_id) == 4

    assert run("done", task_id).returncode == 0
    assert read(env)["tasks"][0]["completedAt"] != ""
    assert run("undo", task_id).returncode == 0
    assert read(env)["tasks"][0]["completedAt"] == ""

    assert run("rm", task_id).returncode == 0
    state = read(env)
    assert state["tasks"] == []
    assert state["trash"][0]["id"] == task_id
    assert run("restore", task_id).returncode == 0
    state = read(env)
    assert state["tasks"][0]["id"] == task_id
    assert state["trash"] == []


def test_subtasks(env):
    task_id = run("add", "apresentação", "--sub", "rascunho", "--sub", "slides").stdout.split()[0]
    task = read(env)["tasks"][0]
    assert [s["id"] for s in task["subtasks"]] == [f"{task_id}.1", f"{task_id}.2"]

    assert run("sub", "add", task_id, "ensaiar").returncode == 0
    assert run("sub", "done", f"{task_id}.1").returncode == 0
    task = read(env)["tasks"][0]
    assert task["subtasks"][0]["done"] is True
    assert task["subtasks"][2]["title"] == "ensaiar"
    assert task["completedAt"] == "", "concluir subpassos não fecha a tarefa mãe"

    assert run("done", task_id).returncode == 0
    assert all(s["done"] for s in read(env)["tasks"][0]["subtasks"]), "concluir a mãe marca os filhos"

    assert run("sub", "rm", f"{task_id}.2").returncode == 0
    assert len(read(env)["tasks"][0]["subtasks"]) == 2


def test_edit_and_snooze(env):
    task_id = run("add", "coisa").stdout.split()[0]
    assert run("edit", task_id, "--due", "amanhã", "--title", "outra coisa").returncode == 0
    task = read(env)["tasks"][0]
    assert task["title"] == "outra coisa"
    assert task["due"] == (date.today() + timedelta(days=1)).isoformat()

    assert run("snooze", task_id, "3").returncode == 0
    assert read(env)["tasks"][0]["due"] == (date.today() + timedelta(days=4)).isoformat()

    assert run("edit", task_id, "--no-due").returncode == 0
    assert read(env)["tasks"][0]["due"] == ""


def test_unknown_id_fails(env):
    result = run("done", "zzzz")
    assert result.returncode == 1
    assert "não existe" in result.stderr


def test_event_add(env):
    assert run("event", "add", "dentista qui 15h-16h30").returncode == 0
    event = read(env)["events"][0]
    assert event["title"] == "dentista"
    assert event["allDay"] is False
    assert event["start"][11:16] == "15:00"
    assert event["end"][11:16] == "16:30"

    assert run("event", "add", "feriado amanhã").returncode == 0
    allday = read(env)["events"][1]
    assert allday["allDay"] is True
    assert allday["start"] == (date.today() + timedelta(days=1)).isoformat()


def test_seed_and_list(env):
    assert run("seed").returncode == 0
    state = read(env)
    assert len(state["tasks"]) >= 5
    assert len(state["events"]) >= 4
    listing = run("list").stdout
    assert "Hoje" in listing and "Atrasadas" in listing
    assert "Concluídas" not in listing
    assert "Concluídas" in run("list", "--all").stdout


def test_prune_old_completed(env):
    task_id = run("add", "velha").stdout.split()[0]
    state = read(env)
    state["tasks"][0]["completedAt"] = "2000-01-01T00:00:00+00:00"
    env.write_text(json.dumps(state), encoding="utf-8")
    run("add", "nova")
    assert [t["title"] for t in read(env)["tasks"]] == ["nova"]
    assert task_id not in [t["id"] for t in read(env)["tasks"]]
