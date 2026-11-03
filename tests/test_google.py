"""Testes do módulo do Google: mapeamento, OAuth sem rede e sincronização com uma API falsa."""

import io
import json
import os
import stat
import sys
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import agenda_google as google  # noqa: E402
import agenda_store as store  # noqa: E402

TZ = timezone(timedelta(hours=-3))
NOW = datetime(2026, 11, 3, 12, 0, tzinfo=TZ)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENDA_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("AGENDA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("AGENDA_NO_KEYRING", "1")
    monkeypatch.setenv("AGENDA_NO_NOTIFY", "1")
    return tmp_path


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def fake_opener(payloads):
    """Devolve um `urlopen` falso que responde, em ordem, os JSONs da lista."""
    calls = []

    def opener(request, timeout=0):
        calls.append(request)
        return FakeResponse(json.dumps(payloads[len(calls) - 1]).encode("utf-8"))

    opener.calls = calls
    return opener


CALENDAR = {"id": "primary", "summary": "Pessoal", "backgroundColor": "#8be9fd", "primary": True}


def test_map_event_com_hora_dia_todo_e_cancelado():
    timed = google.map_event({
        "id": "abc", "summary": " Dentista ", "status": "confirmed",
        "start": {"dateTime": "2026-11-03T15:00:00-03:00"}, "end": {"dateTime": "2026-11-03T16:00:00-03:00"},
        "location": "Centro", "hangoutLink": "https://meet.google.com/x", "htmlLink": "https://calendar/x",
    }, CALENDAR)
    assert timed == {
        "id": "g:abc", "calendar": "Pessoal", "calendarId": "primary", "color": "#8be9fd", "title": "Dentista",
        "allDay": False, "start": "2026-11-03T15:00:00-03:00", "end": "2026-11-03T16:00:00-03:00",
        "location": "Centro", "url": "https://meet.google.com/x", "description": "",
    }
    all_day = google.map_event({"id": "d", "summary": "Feriado", "start": {"date": "2026-11-15"}, "end": {"date": "2026-11-16"}}, CALENDAR)
    assert all_day["allDay"] is True and all_day["start"] == "2026-11-15" and all_day["end"] == "2026-11-16"
    assert google.map_event({"id": "c", "status": "cancelled", "start": {"date": "2026-11-15"}}, CALENDAR) is None
    untitled = google.map_event({"id": "u", "start": {"date": "2026-11-15"}, "end": {"date": "2026-11-16"}}, CALENDAR)
    assert untitled["title"] == "(sem título)"


def test_meeting_link_cai_para_conferencia_e_depois_para_htmlLink():
    conf = {"conferenceData": {"entryPoints": [{"entryPointType": "phone", "uri": "tel:1"}, {"entryPointType": "video", "uri": "https://v"}]}, "htmlLink": "h"}
    assert google.meeting_link(conf) == "https://v"
    assert google.meeting_link({"htmlLink": "h"}) == "h"
    assert google.meeting_link({}) == ""


def test_build_auth_url_tem_pkce_e_offline():
    verifier, challenge = google.pkce_pair()
    assert len(verifier) >= 43 and "=" not in challenge
    url = google.build_auth_url("cid", "http://127.0.0.1:1234", "st", challenge)
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
    assert query["client_id"] == "cid"
    assert query["code_challenge"] == challenge
    assert query["code_challenge_method"] == "S256"
    assert query["access_type"] == "offline"
    assert query["prompt"] == "consent"
    assert all(scope in query["scope"] for scope in google.SCOPES)


def test_credentials_renovam_token_vencido_e_guardam(env):
    token_store = google.TokenStore(path=str(env / "config" / "token.json"), use_keyring=False)
    token_store.save({"access_token": "velho", "refresh_token": "r", "expires_at": 0})
    assert stat.S_IMODE(os.stat(token_store.path).st_mode) == 0o600

    opener = fake_opener([{"access_token": "novo", "expires_in": 3600, "token_type": "Bearer"}])
    creds = google.Credentials({"client_id": "c", "client_secret": "s"}, token_store, opener=opener)
    assert creds.access_token() == "novo"
    assert len(opener.calls) == 1
    sent = dict(urllib.parse.parse_qsl(opener.calls[0].data.decode("ascii")))
    assert sent["grant_type"] == "refresh_token" and sent["refresh_token"] == "r"
    saved = json.load(open(token_store.path, encoding="utf-8"))
    assert saved["access_token"] == "novo" and saved["refresh_token"] == "r" and saved["expires_at"] > 0
    # Com o token válido, não há segunda chamada.
    assert creds.access_token() == "novo"
    assert len(opener.calls) == 1


def test_credentials_sem_token_falam_para_autorizar(env):
    creds = google.Credentials({"client_id": "c", "client_secret": "s"}, google.TokenStore(path=str(env / "t.json"), use_keyring=False))
    with pytest.raises(google.GoogleError, match="google auth"):
        creds.access_token()


class FakeApi:
    def __init__(self, calendars, events_by_calendar, error=None):
        self.calendars = calendars
        self.events_by_calendar = events_by_calendar
        self.error = error
        self.calls = []

    def calendar_list(self):
        if self.error:
            raise google.GoogleError(self.error)
        return self.calendars

    def events(self, calendar_id, time_min, time_max):
        self.calls.append((calendar_id, time_min, time_max))
        return self.events_by_calendar.get(calendar_id, [])


def test_sync_into_state_troca_eventos_do_google_e_preserva_locais(env):
    with store.locked_state() as state:
        state["events"] = [
            {"id": "l:aaaa", "calendar": "local", "title": "Local", "start": "2026-11-04", "end": "2026-11-05", "allDay": True},
            {"id": "g:velho", "calendar": "Pessoal", "title": "Velho", "start": "2026-11-01", "end": "2026-11-02", "allDay": True},
        ]
    api = FakeApi([CALENDAR, {"id": "work@x", "summary": "Trabalho", "backgroundColor": "#f00"}], {
        "primary": [{"id": "n1", "summary": "Novo", "start": {"date": "2026-11-05"}, "end": {"date": "2026-11-06"}}],
        "work@x": [{"id": "w1", "summary": "Reunião", "start": {"dateTime": "2026-11-04T10:00:00-03:00"}, "end": {"dateTime": "2026-11-04T11:00:00-03:00"}}],
    })
    config = google.load_config()
    config["google"]["calendars"] = ["primary", "work@x"]
    count = google.sync_into_state(api, config, now=NOW)
    assert count == 2
    state = store.read_state()
    assert [e["id"] for e in state["events"]] == ["l:aaaa", "g:n1", "g:w1"]
    assert state["events"][2]["calendar"] == "Trabalho" and state["events"][2]["color"] == "#f00"
    assert state["sync"]["status"] == "ok" and state["sync"]["lastOkAt"].startswith("2026-11-03T12:00")
    # Janela: um dia para trás, catorze para frente, em dias inteiros.
    calendar_id, time_min, time_max = api.calls[0]
    assert time_min == datetime(2026, 11, 2, 0, 0, tzinfo=TZ)
    assert time_max == datetime(2026, 11, 18, 0, 0, tzinfo=TZ)


def test_sync_com_erro_mantem_eventos_e_marca_erro(env):
    with store.locked_state() as state:
        state["events"] = [{"id": "g:velho", "calendar": "Pessoal", "title": "Velho", "start": "2026-11-01", "end": "2026-11-02", "allDay": True}]
        state["sync"] = {"lastOkAt": "2026-11-03T08:00:00-03:00", "status": "ok", "error": ""}
    api = FakeApi([], {}, error="sem conexão")
    with pytest.raises(google.GoogleError):
        google.sync_into_state(api, google.load_config(), now=NOW)
    state = store.read_state()
    assert [e["id"] for e in state["events"]] == ["g:velho"]
    assert state["sync"] == {"lastOkAt": "2026-11-03T08:00:00-03:00", "status": "error", "error": "sem conexão"}


def test_event_body_com_hora_e_dia_todo():
    timed = google.event_body("Dentista", date(2026, 11, 5), "15:00", None, TZ)
    assert timed == {"summary": "Dentista", "start": {"dateTime": "2026-11-05T15:00:00-03:00"}, "end": {"dateTime": "2026-11-05T16:00:00-03:00"}}
    ranged = google.event_body("Plantão", date(2026, 11, 5), "22:00", "02:00", TZ)
    assert ranged["end"] == {"dateTime": "2026-11-06T02:00:00-03:00"}
    all_day = google.event_body("Feriado", date(2026, 11, 15), None, None, TZ)
    assert all_day == {"summary": "Feriado", "start": {"date": "2026-11-15"}, "end": {"date": "2026-11-16"}}


def test_load_config_usa_defaults_e_le_o_arquivo(env):
    assert google.load_config()["google"]["calendars"] == ["primary"]
    google.ensure_config_file()
    assert "calendars" in Path(google.config_path()).read_text(encoding="utf-8")
    Path(google.config_path()).write_text('[google]\ncalendars = "work@x"\nsync_minutes = 2\n[reminders]\nmorning_summary = "08:00"\n', encoding="utf-8")
    config = google.load_config()
    assert config["google"]["calendars"] == ["work@x"]
    assert config["google"]["sync_minutes"] == 2
    assert config["google"]["days_ahead"] == 14
    assert config["reminders"]["morning_summary"] == "08:00"
    Path(google.config_path()).write_text("isto não é toml = = =", encoding="utf-8")
    with pytest.raises(google.GoogleError):
        google.load_config()


def test_load_client_exige_arquivo_valido(env):
    with pytest.raises(google.GoogleError, match="google setup"):
        google.load_client()
    source = env / "baixado.json"
    source.write_text(json.dumps({"installed": {"client_id": "abc", "client_secret": "xyz"}}), encoding="utf-8")
    target = google.install_client_secret(str(source))
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600
    assert google.load_client() == {"client_id": "abc", "client_secret": "xyz"}
    assert google.is_configured() is False  # ainda sem token
    # Rodar o setup apontando para o arquivo já instalado não pode falhar.
    assert google.install_client_secret(target) == target
    assert google.load_client() == {"client_id": "abc", "client_secret": "xyz"}
