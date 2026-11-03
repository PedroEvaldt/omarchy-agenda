"""O agendad: sincroniza de tempos em tempos e manda lembretes.

Um laço só, sem threads: a cada volta ele vê se é hora de sincronizar, se
algum evento começa daqui a pouco e se o resumo do dia ainda não saiu. Roda
como serviço `systemd --user`, então `journalctl --user -u agendad` mostra o
que ele anda fazendo.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from datetime import datetime, timedelta

import agenda_google as google
import agenda_store as store
import agenda_telegram as telegram

log = logging.getLogger("agendad")

SERVICE_NAME = "agendad.service"
TICK_SECONDS = 30
CALENDAR_GLYPH = "󰃭"


# ---------------------------------------------------------------------------
# O que já foi avisado
# ---------------------------------------------------------------------------


def notified_path() -> str:
    return os.path.join(store.state_dir(), "notified.json")


def load_notified() -> dict:
    try:
        with open(notified_path(), encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        data = {}
    return {"events": dict(data.get("events") or {}), "summaryDate": str(data.get("summaryDate") or "")}


def save_notified(data: dict, now: datetime) -> None:
    # Esquece avisos com mais de dois dias para o arquivo não crescer.
    cutoff = store.iso(now - timedelta(days=2))
    data["events"] = {key: when for key, when in data["events"].items() if when >= cutoff}
    os.makedirs(store.state_dir(), exist_ok=True)
    with open(notified_path(), "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Lembretes
# ---------------------------------------------------------------------------


def parse_start(event: dict) -> datetime | None:
    if event.get("allDay"):
        return None
    try:
        return datetime.fromisoformat(str(event.get("start", "")))
    except ValueError:
        return None


def due_reminders(events: list[dict], now: datetime, minutes_before: int, notified: dict) -> list[dict]:
    """Eventos com hora que começam dentro da janela e ainda não foram avisados."""
    window_end = now + timedelta(minutes=minutes_before)
    due = []
    for event in events:
        start = parse_start(event)
        if start is None or event.get("id") in notified:
            continue
        # Um evento que começou há pouco ainda merece aviso; um de ontem, não.
        if now - timedelta(minutes=2) <= start <= window_end:
            due.append(event)
    return sorted(due, key=lambda e: e["start"])


def reminder_text(event: dict, now: datetime) -> tuple[str, str]:
    start = parse_start(event)
    minutes = max(0, int((start - now).total_seconds() // 60)) if start else 0
    when = "agora" if minutes == 0 else f"em {minutes} min"
    title = f"{event.get('title', 'Evento')} {when}"
    bits = [start.strftime("%H:%M") if start else ""]
    try:
        end = datetime.fromisoformat(str(event.get("end", "")))
        bits[0] += "–" + end.strftime("%H:%M")
    except ValueError:
        pass
    if event.get("location"):
        bits.append(event["location"])
    return title, " · ".join(b for b in bits if b)


def send_reminders(state: dict, now: datetime, minutes_before: int, notified: dict) -> int:
    sent = 0
    for event in due_reminders(state["events"], now, minutes_before, notified["events"]):
        title, body = reminder_text(event, now)
        action = ("Abrir", ["xdg-open", event["url"]]) if event.get("url") else None
        store.notify(title, body, glyph=CALENDAR_GLYPH, action=action)
        log.info("lembrete: %s", title)
        notified["events"][event["id"]] = store.iso(now)
        sent += 1
    return sent


# ---------------------------------------------------------------------------
# Resumo da manhã
# ---------------------------------------------------------------------------


def morning_summary_due(configured: str, now: datetime, last_date: str) -> bool:
    """Uma vez por dia, a partir da hora configurada."""
    if not configured:
        return False
    try:
        hour, minute = (int(x) for x in configured.split(":"))
    except ValueError:
        return False
    today = now.date().isoformat()
    return last_date != today and (now.hour, now.minute) >= (hour, minute)


def summary_text(state: dict, now: datetime) -> tuple[str, str]:
    today = now.date().isoformat()
    tasks = [t for t in state["tasks"] if not t.get("completedAt") and t.get("due") and t["due"] <= today]
    events = []
    for event in state["events"]:
        start = str(event.get("start", ""))
        if start[:10] == today:
            events.append(event)
    events.sort(key=lambda e: (not e.get("allDay"), e.get("start", "")))
    lines = []
    for event in events[:4]:
        start = parse_start(event)
        lines.append(f"{start.strftime('%H:%M') if start else 'dia todo'}  {event.get('title', '')}")
    for task in sorted(tasks, key=lambda t: (t["due"], t.get("dueTime", "")))[:4]:
        lines.append(f"{'󰄱'}  {task['title']}")
    title = f"Hoje: {len(events)} evento{'s' if len(events) != 1 else ''}, {len(tasks)} tarefa{'s' if len(tasks) != 1 else ''}"
    return title, "\n".join(lines) if lines else "Dia livre."


# ---------------------------------------------------------------------------
# O laço
# ---------------------------------------------------------------------------


def run(config: dict, once: bool = False) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sync_minutes = max(1, int(config["google"]["sync_minutes"]))
    minutes_before = max(0, int(config["reminders"]["minutes_before"]))
    summary_at = str(config["reminders"]["morning_summary"] or "")
    api = None
    next_sync = 0.0
    bot = None
    creds = telegram.load_credentials()
    if creds and creds["chat_id"]:
        bot = telegram.Bot(creds["token"], creds["chat_id"])
    log.info("agendad iniciado: sync a cada %d min, lembrete %d min antes, telegram %s",
             sync_minutes, minutes_before, "ligado" if bot else "desligado")

    while True:
        now = store.now_local()
        if time.time() >= next_sync:
            next_sync = time.time() + sync_minutes * 60
            if google.is_configured():
                try:
                    api = api or google.connect()
                    count = google.sync_into_state(api, config, now=now)
                    log.info("sync ok: %d eventos", count)
                except google.GoogleError as error:
                    log.warning("sync falhou: %s", error)
                    api = None
            else:
                log.info("Google não configurado; só lembretes de eventos locais")

        try:
            state = store.read_state()
        except store.StoreError as error:
            log.warning("%s", error)
            state = store.empty_state()
        notified = load_notified()
        changed = send_reminders(state, now, minutes_before, notified) > 0
        if morning_summary_due(summary_at, now, notified["summaryDate"]):
            title, body = summary_text(state, now)
            store.notify(title, body, glyph=CALENDAR_GLYPH)
            log.info("resumo do dia enviado")
            notified["summaryDate"] = now.date().isoformat()
            changed = True
        if changed:
            save_notified(notified, now)

        if once:
            return
        # Com o Telegram ligado, a espera por mensagens é o próprio sono do laço:
        # a chamada volta na hora em que algo chega, ou no fim do tempo.
        if bot:
            try:
                bot.serve_once(timeout=TICK_SECONDS - 5)
            except telegram.TelegramError as error:
                log.warning("telegram: %s", error)
                time.sleep(10)
        else:
            time.sleep(TICK_SECONDS)


# ---------------------------------------------------------------------------
# Serviço do systemd
# ---------------------------------------------------------------------------


def unit_path() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "systemd", "user", SERVICE_NAME)


def unit_text(executable: str) -> str:
    return f"""[Unit]
Description=Agenda: sincronização com o Google Calendar e lembretes
After=graphical-session.target

[Service]
ExecStart={executable} daemon
Restart=on-failure
RestartSec=15

[Install]
WantedBy=default.target
"""


def systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, check=False)


def install_service(executable: str) -> str:
    path = unit_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(unit_text(executable))
    for step in (("daemon-reload",), ("enable", "--now", SERVICE_NAME)):
        result = systemctl(*step)
        if result.returncode != 0:
            raise RuntimeError(f"systemctl --user {' '.join(step)} falhou: {result.stderr.strip()}")
    return path


def uninstall_service() -> None:
    systemctl("disable", "--now", SERVICE_NAME)
    path = unit_path()
    if os.path.exists(path):
        os.unlink(path)
    systemctl("daemon-reload")


def service_status() -> str:
    result = systemctl("is-active", SERVICE_NAME)
    return result.stdout.strip() or result.stderr.strip() or "desconhecido"
