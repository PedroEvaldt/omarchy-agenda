"""Google Calendar: configuração, OAuth 2.0 e sincronização, só com biblioteca padrão.

As peças, na ordem em que você as encontra ao configurar:

1. `config.toml`: quais calendários sincronizar, de quantos em quantos
   minutos, quantos dias para frente. Nada secreto.
2. `client_secret.json`: a identidade do SEU app no Google, baixada do
   Google Cloud. Diz ao Google "quem está pedindo acesso".
3. Autorização: abre o navegador, você aprova, o Google devolve um código
   para um servidor HTTP minúsculo que sobe aqui por alguns segundos
   (o "loopback"). O código vira um token de acesso (dura uma hora) e um
   refresh token (dura meses) e é com esse que renovamos sem incomodar você.
4. Sincronização: lista os eventos de cada calendário numa janela de dias e
   troca os eventos do Google no state.json pelos novos. Eventos locais
   ficam como estão.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets
import shutil
import subprocess
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import date, datetime, timedelta

import agenda_store as store

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API_BASE = "https://www.googleapis.com/calendar/v3"
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
]

DEFAULT_CONFIG = """# Configuração do plugin Agenda. Segredos não ficam aqui:
# o client_secret.json e o token moram ao lado, fora do git.

[google]
# Ids dos calendários a sincronizar. "primary" é o calendário principal da conta;
# `agenda google calendars` lista os outros com seus ids.
calendars = ["primary"]
# Onde `agenda event add` cria eventos.
write_calendar = "primary"
sync_minutes = 5
days_back = 1
days_ahead = 14

[reminders]
# Avisa este tanto de minutos antes de cada evento com hora.
minutes_before = 10
# Hora do resumo do dia, "08:00" por exemplo. Vazio desliga.
morning_summary = ""
"""

DEFAULTS = {
    "google": {"calendars": ["primary"], "write_calendar": "primary", "sync_minutes": 5, "days_back": 1, "days_ahead": 14},
    "reminders": {"minutes_before": 10, "morning_summary": ""},
}


class GoogleError(Exception):
    """Erro de configuração, autorização ou da API, com mensagem para o usuário."""


# ---------------------------------------------------------------------------
# Configuração e credenciais
# ---------------------------------------------------------------------------


def config_path() -> str:
    return os.path.join(store.config_dir(), "config.toml")


def client_secret_path() -> str:
    return os.path.join(store.config_dir(), "client_secret.json")


def token_file_path() -> str:
    return os.path.join(store.config_dir(), "token.json")


def ensure_config_file() -> str:
    path = config_path()
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(DEFAULT_CONFIG)
    return path


def load_config() -> dict:
    """Defaults cobertos pelo que estiver no config.toml."""
    config = {section: dict(values) for section, values in DEFAULTS.items()}
    try:
        with open(config_path(), "rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        return config
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise GoogleError(f"config.toml inválido: {error}") from error
    for section in config:
        if isinstance(data.get(section), dict):
            config[section].update(data[section])
    calendars = config["google"].get("calendars")
    if isinstance(calendars, str):
        config["google"]["calendars"] = [calendars]
    return config


def load_client() -> dict:
    """Lê client_id e client_secret do JSON baixado do Google Cloud."""
    try:
        with open(client_secret_path(), encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        raise GoogleError("falta o client_secret.json; rode `agenda google setup <arquivo.json>`") from None
    except (OSError, json.JSONDecodeError) as error:
        raise GoogleError(f"client_secret.json ilegível: {error}") from error
    inner = data.get("installed") or data.get("web") or data
    client_id, client_secret = inner.get("client_id"), inner.get("client_secret")
    if not client_id or not client_secret:
        raise GoogleError("client_secret.json sem client_id ou client_secret; baixe o de um cliente do tipo 'App para computador'")
    return {"client_id": client_id, "client_secret": client_secret}


def install_client_secret(source: str) -> str:
    with open(source, encoding="utf-8") as handle:
        json.load(handle)  # valida antes de copiar
    target = client_secret_path()
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copyfile(source, target)
    os.chmod(target, 0o600)
    return target


class TokenStore:
    """Guarda o token no keyring do sistema (secret-tool) ou, sem ele, num arquivo 0600.

    Os dois caminhos existem porque nem toda instalação tem um serviço de
    segredos rodando; o arquivo é a rede de segurança.
    """

    LABEL = "Agenda: token do Google Calendar"
    ATTRS = ["service", "agenda", "account", "google"]

    def __init__(self, path: str | None = None, use_keyring: bool | None = None):
        self.path = path or token_file_path()
        if use_keyring is None:
            use_keyring = not os.environ.get("AGENDA_NO_KEYRING") and shutil.which("secret-tool") is not None
        self.use_keyring = use_keyring

    def _keyring(self, args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess | None:
        try:
            return subprocess.run(["secret-tool", *args], input=stdin, capture_output=True, text=True, timeout=10, check=False)
        except (OSError, subprocess.SubprocessError):
            return None

    def load(self) -> dict | None:
        if self.use_keyring:
            result = self._keyring(["lookup", *self.ATTRS])
            if result and result.returncode == 0 and result.stdout.strip():
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    pass
        try:
            with open(self.path, encoding="utf-8") as handle:
                return json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

    def save(self, token: dict) -> str:
        payload = json.dumps(token)
        if self.use_keyring:
            result = self._keyring(["store", f"--label={self.LABEL}", *self.ATTRS], stdin=payload)
            if result and result.returncode == 0:
                # Um arquivo antigo não pode ficar para trás com um token velho.
                if os.path.exists(self.path):
                    os.unlink(self.path)
                return "keyring"
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        return "arquivo"

    def clear(self) -> None:
        if self.use_keyring:
            self._keyring(["clear", *self.ATTRS])
        if os.path.exists(self.path):
            os.unlink(self.path)


def is_configured() -> bool:
    return os.path.exists(client_secret_path()) and TokenStore().load() is not None


# ---------------------------------------------------------------------------
# OAuth 2.0 (fluxo de app instalado, com PKCE e loopback)
# ---------------------------------------------------------------------------


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def pkce_pair() -> tuple[str, str]:
    """PKCE: um segredo de uma vez só que prova que quem troca o código é quem pediu."""
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def build_auth_url(client_id: str, redirect_uri: str, state: str, challenge: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",   # pede o refresh token
        "prompt": "consent",        # garante que ele venha mesmo em reautorização
    }
    return AUTH_URL + "?" + urllib.parse.urlencode(params)


def post_form(url: str, fields: dict, opener=None) -> dict:
    data = urllib.parse.urlencode(fields).encode("ascii")
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    open_fn = opener or urllib.request.urlopen
    try:
        with open_fn(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        raise GoogleError(f"o Google recusou ({error.code}): {detail[:300]}") from error
    except urllib.error.URLError as error:
        raise GoogleError(f"sem conexão com o Google: {error.reason}") from error


def with_expiry(token: dict, now: float | None = None) -> dict:
    now = now if now is not None else time.time()
    token = dict(token)
    token["expires_at"] = now + float(token.get("expires_in", 3600))
    return token


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Recebe o redirecionamento do Google com o código e responde uma página curta."""

    captured: dict = {}

    def do_GET(self):  # noqa: N802 (nome exigido pelo http.server)
        query = urllib.parse.urlparse(self.path).query
        _CallbackHandler.captured = dict(urllib.parse.parse_qsl(query))
        ok = "code" in _CallbackHandler.captured
        body = (
            "<html><body style='font-family:sans-serif;padding:2em'>"
            + ("<h2>Agenda autorizada.</h2><p>Pode fechar esta aba e voltar ao terminal.</p>" if ok
               else "<h2>Autorização recusada.</h2><p>Volte ao terminal.</p>")
            + "</body></html>"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):  # silencia o log padrão do servidor
        return


def authorize(client: dict, open_browser: bool = True, timeout: int = 300) -> dict:
    """Conduz a autorização no navegador e devolve o token já com expires_at."""
    server = http.server.HTTPServer(("127.0.0.1", 0), _CallbackHandler)
    server.timeout = timeout
    port = server.server_address[1]
    redirect_uri = f"http://127.0.0.1:{port}"
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(16)
    url = build_auth_url(client["client_id"], redirect_uri, state, challenge)

    print("Abra este endereço no navegador, se ele não abrir sozinho:\n")
    print(url + "\n")
    if open_browser:
        webbrowser.open(url)
    _CallbackHandler.captured = {}
    server.handle_request()  # espera exatamente uma requisição
    server.server_close()

    answer = _CallbackHandler.captured
    if not answer:
        raise GoogleError("o navegador não voltou com a resposta a tempo")
    if answer.get("state") != state:
        raise GoogleError("resposta com state diferente do pedido; tente de novo")
    if "code" not in answer:
        raise GoogleError(f"autorização recusada: {answer.get('error', 'sem código')}")

    token = post_form(TOKEN_URL, {
        "code": answer["code"],
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": verifier,
    })
    if "refresh_token" not in token:
        raise GoogleError("o Google não devolveu refresh token; revogue o acesso em myaccount.google.com/permissions e autorize de novo")
    return with_expiry(token)


def refresh(token: dict, client: dict, opener=None) -> dict:
    """Troca o refresh token por um access token novo. O refresh token continua o mesmo."""
    fresh = post_form(TOKEN_URL, {
        "refresh_token": token["refresh_token"],
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "grant_type": "refresh_token",
    }, opener=opener)
    merged = dict(token)
    merged.update(fresh)
    return with_expiry(merged)


class Credentials:
    """Entrega um access token válido, renovando e guardando quando preciso."""

    def __init__(self, client: dict, token_store: TokenStore, opener=None):
        self.client = client
        self.store = token_store
        self.opener = opener
        self.token = token_store.load()

    def access_token(self, force: bool = False) -> str:
        if not self.token or "refresh_token" not in self.token:
            raise GoogleError("Google ainda não autorizado; rode `agenda google auth`")
        if force or time.time() >= float(self.token.get("expires_at", 0)) - 60:
            self.token = refresh(self.token, self.client, opener=self.opener)
            self.store.save(self.token)
        return self.token["access_token"]


# ---------------------------------------------------------------------------
# API REST do Calendar
# ---------------------------------------------------------------------------


class Api:
    """Chamadas mínimas à API v3. Tudo é JSON para lá e para cá."""

    def __init__(self, credentials: Credentials, opener=None):
        self.credentials = credentials
        self.opener = opener or urllib.request.urlopen

    def request(self, method: str, path: str, params: dict | None = None, body: dict | None = None, _retry: bool = True) -> dict:
        url = API_BASE + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", "Bearer " + self.credentials.access_token())
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with self.opener(request, timeout=30) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as error:
            if error.code == 401 and _retry:
                # Token recusado: força uma renovação e tenta uma vez.
                self.credentials.access_token(force=True)
                return self.request(method, path, params, body, _retry=False)
            detail = error.read().decode("utf-8", "replace")
            try:
                detail = json.loads(detail)["error"]["message"]
            except (ValueError, KeyError, TypeError):
                pass
            raise GoogleError(f"API do Calendar respondeu {error.code}: {detail[:300]}") from error
        except urllib.error.URLError as error:
            raise GoogleError(f"sem conexão com o Google: {error.reason}") from error

    def calendar_list(self) -> list[dict]:
        return self.request("GET", "/users/me/calendarList").get("items", [])

    def events(self, calendar_id: str, time_min: datetime, time_max: datetime) -> list[dict]:
        items: list[dict] = []
        page = None
        while True:
            params = {
                "timeMin": store.iso(time_min),
                "timeMax": store.iso(time_max),
                "singleEvents": "true",   # expande recorrências em instâncias
                "orderBy": "startTime",
                "maxResults": 250,
            }
            if page:
                params["pageToken"] = page
            data = self.request("GET", f"/calendars/{urllib.parse.quote(calendar_id, safe='')}/events", params)
            items.extend(data.get("items", []))
            page = data.get("nextPageToken")
            if not page:
                return items

    def insert_event(self, calendar_id: str, body: dict) -> dict:
        return self.request("POST", f"/calendars/{urllib.parse.quote(calendar_id, safe='')}/events", body=body)

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        self.request("DELETE", f"/calendars/{urllib.parse.quote(calendar_id, safe='')}/events/{urllib.parse.quote(event_id, safe='')}")


def connect(opener=None) -> Api:
    """Monta credenciais e API a partir dos arquivos de configuração."""
    return Api(Credentials(load_client(), TokenStore(), opener=opener), opener=opener)


# ---------------------------------------------------------------------------
# Do formato do Google para o do state.json
# ---------------------------------------------------------------------------


def meeting_link(item: dict) -> str:
    if item.get("hangoutLink"):
        return item["hangoutLink"]
    for entry in (item.get("conferenceData") or {}).get("entryPoints", []) or []:
        if entry.get("entryPointType") == "video" and entry.get("uri"):
            return entry["uri"]
    return item.get("htmlLink", "")


def map_event(item: dict, calendar: dict) -> dict | None:
    """Um evento da API vira um evento do nosso formato; cancelados somem."""
    if item.get("status") == "cancelled":
        return None
    start, end = item.get("start") or {}, item.get("end") or {}
    all_day = "date" in start
    start_value = start.get("date") if all_day else start.get("dateTime")
    if not start_value:
        return None
    return {
        "id": "g:" + str(item.get("id", "")),
        "calendar": calendar.get("summary", calendar.get("id", "")),
        "calendarId": calendar.get("id", ""),
        "color": calendar.get("backgroundColor", ""),
        "title": (item.get("summary") or "(sem título)").strip(),
        "allDay": all_day,
        "start": start_value,
        "end": (end.get("date") if all_day else end.get("dateTime")) or "",
        "location": item.get("location", "") or "",
        "url": meeting_link(item),
        "description": (item.get("description") or "")[:2000],
    }


def fetch_events(api: Api, config: dict, now: datetime | None = None) -> list[dict]:
    """Todos os eventos dos calendários configurados, na janela de dias."""
    now = now or store.now_local()
    google = config["google"]
    time_min = (now - timedelta(days=int(google["days_back"]))).replace(hour=0, minute=0, second=0, microsecond=0)
    time_max = (now + timedelta(days=int(google["days_ahead"]) + 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    known = {cal.get("id"): cal for cal in api.calendar_list()}
    events: list[dict] = []
    for calendar_id in google["calendars"]:
        meta = known.get(calendar_id)
        if meta is None and calendar_id == "primary":
            meta = next((c for c in known.values() if c.get("primary")), {"id": "primary", "summary": "Principal"})
        meta = dict(meta or {"id": calendar_id, "summary": calendar_id})
        # O id que o usuário escreveu ("primary") é o que usamos para apagar depois.
        meta["id"] = calendar_id
        for item in api.events(calendar_id, time_min, time_max):
            mapped = map_event(item, meta)
            if mapped:
                events.append(mapped)
    return events


def merge_events(current: list[dict], fresh: list[dict]) -> list[dict]:
    """Troca os eventos do Google pelos novos e preserva os locais."""
    local = [e for e in current if not str(e.get("id", "")).startswith("g:")]
    return local + fresh


def sync_into_state(api: Api, config: dict, path: str | None = None, now: datetime | None = None) -> int:
    """Sincroniza e grava. Em erro, mantém os eventos antigos e registra a falha no `sync`."""
    now = now or store.now_local()
    try:
        fresh = fetch_events(api, config, now)
    except GoogleError as error:
        with store.locked_state(path) as state:
            state["sync"] = {"lastOkAt": state["sync"].get("lastOkAt", ""), "status": "error", "error": str(error)}
        raise
    with store.locked_state(path) as state:
        state["events"] = merge_events(state["events"], fresh)
        state["sync"] = {"lastOkAt": store.iso(now), "status": "ok", "error": ""}
    return len(fresh)


# ---------------------------------------------------------------------------
# Do nosso formato para o do Google
# ---------------------------------------------------------------------------


def event_body(title: str, day: date, start_time: str | None, end_time: str | None, tz, default_minutes: int = 60) -> dict:
    """Corpo de um evento novo, a partir do que o parser de texto entendeu."""
    body = {"summary": title}
    if start_time:
        start = datetime.combine(day, datetime.strptime(start_time, "%H:%M").time(), tzinfo=tz)
        if end_time:
            end = datetime.combine(day, datetime.strptime(end_time, "%H:%M").time(), tzinfo=tz)
            if end <= start:
                end += timedelta(days=1)
        else:
            end = start + timedelta(minutes=default_minutes)
        body["start"] = {"dateTime": store.iso(start)}
        body["end"] = {"dateTime": store.iso(end)}
    else:
        body["start"] = {"date": day.isoformat()}
        body["end"] = {"date": (day + timedelta(days=1)).isoformat()}
    return body
