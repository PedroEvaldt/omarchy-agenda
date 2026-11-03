"""Arquivo de estado do plugin Agenda: caminhos, leitura, escrita atômica e trava.

Tudo que mexe no state.json passa por aqui. A partir da fase 2 dois
processos escrevem nele, a CLI e o daemon, então a escrita é sempre:

    with locked_state() as state:   # pega a trava, lê
        ...muda o dicionário...
    # ao sair do bloco: grava num temporário, troca de lugar, solta a trava

A trava é um flock num arquivo ao lado. O painel só lê, e lê o arquivo
inteiro de uma vez, por isso a troca atômica basta para ele nunca ver
um JSON pela metade.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta

# Concluídas somem do arquivo depois deste prazo; a lixeira também.
RETENTION_DAYS = 7


class StoreError(Exception):
    """Arquivo de estado ilegível."""


# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------


def config_dir() -> str:
    """~/.config/agenda, trocável por AGENDA_CONFIG_DIR nos testes."""
    override = os.environ.get("AGENDA_CONFIG_DIR")
    if override:
        return override
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "agenda")


def state_path() -> str:
    """Caminho do state.json. AGENDA_STATE permite trocar nos testes."""
    override = os.environ.get("AGENDA_STATE")
    if override:
        return override
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(base, "agenda", "state.json")


def state_dir() -> str:
    return os.path.dirname(state_path()) or "."


# ---------------------------------------------------------------------------
# Tempo
# ---------------------------------------------------------------------------


def now_local() -> datetime:
    return datetime.now().astimezone()


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Estado
# ---------------------------------------------------------------------------


def empty_state() -> dict:
    return {
        "version": 1,
        "generatedAt": "",
        "sync": {"lastOkAt": "", "status": "none", "error": ""},
        "tasks": [],
        "events": [],
        "trash": [],
    }


def read_state(path: str | None = None) -> dict:
    path = path or state_path()
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return empty_state()
    except (OSError, json.JSONDecodeError) as error:
        raise StoreError(f"não consegui ler {path}: {error}") from error
    state = empty_state()
    if isinstance(data, dict):
        for key in ("tasks", "events", "trash"):
            if isinstance(data.get(key), list):
                state[key] = data[key]
        if isinstance(data.get("sync"), dict):
            state["sync"].update(data["sync"])
    return state


def prune(state: dict, now: datetime) -> None:
    """Esquece concluídas e excluídas velhas para o arquivo não crescer para sempre."""
    cutoff = iso(now - timedelta(days=RETENTION_DAYS))
    state["tasks"] = [t for t in state["tasks"] if not t.get("completedAt") or t["completedAt"] >= cutoff]
    state["trash"] = [t for t in state["trash"] if t.get("deletedAt", "") >= cutoff]


def write_state(path: str, state: dict) -> None:
    """Escrita atômica: grava num temporário e troca de lugar com o arquivo real."""
    now = now_local()
    prune(state, now)
    state["generatedAt"] = iso(now)
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".state-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


@contextlib.contextmanager
def locked_state(path: str | None = None):
    """Lê o estado com a trava e grava ao sair do bloco.

    Se o bloco levantar uma exceção (um `fail()`, por exemplo), nada é gravado
    e a trava é solta do mesmo jeito.
    """
    path = path or state_path()
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    with open(path + ".lock", "w", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        state = read_state(path)
        yield state
        write_state(path, state)


# ---------------------------------------------------------------------------
# Notificações do Omarchy (opcionais)
# ---------------------------------------------------------------------------


def notify(title: str, body: str = "", glyph: str = "󰄲", action: tuple[str, list[str]] | None = None) -> bool:
    """Usa o omarchy-notification-send quando ele existe; fora do Omarchy, silêncio."""
    if os.environ.get("AGENDA_NO_NOTIFY") or not shutil.which("omarchy-notification-send"):
        return False
    command = ["omarchy-notification-send", "-g", glyph, title, body]
    if action:
        label, program = action
        command += ["--action", label, *program]
    try:
        subprocess.run(command, check=False, timeout=5, capture_output=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False
