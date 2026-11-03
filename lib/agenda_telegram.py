"""Canal Telegram: long polling e botões inline, só com urllib.

O bot não precisa de URL pública: ele pergunta ao Telegram, de tempos em
tempos, se chegou algo (getUpdates com timeout). A chamada fica presa até
chegar uma mensagem ou o tempo acabar, então ela serve de "sono" do laço do
agendad. Só o chat pareado é atendido; o resto é ignorado.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

import agenda_bridge as bridge
import agenda_store as store

log = logging.getLogger("telegram")

API = "https://api.telegram.org/bot{token}/{method}"


class TelegramError(Exception):
    """Rede fora, token inválido ou resposta inesperada."""


# ---------------------------------------------------------------------------
# Credenciais: token do BotFather e o id do seu chat, fora do git, 0600
# ---------------------------------------------------------------------------


def credentials_path() -> str:
    return os.path.join(store.config_dir(), "telegram.json")


def load_credentials() -> dict | None:
    try:
        with open(credentials_path(), encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    if not data.get("token"):
        return None
    return {"token": str(data["token"]), "chat_id": int(data.get("chat_id") or 0)}


def save_credentials(token: str, chat_id: int) -> str:
    path = credentials_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump({"token": token, "chat_id": chat_id}, handle)
    return path


def is_configured() -> bool:
    creds = load_credentials()
    return bool(creds and creds["chat_id"])


# ---------------------------------------------------------------------------
# O bot
# ---------------------------------------------------------------------------


def http_call(token: str, method: str, params: dict, timeout: int = 40) -> dict:
    """Uma chamada à API do Bot. Toda resposta vem como {"ok": bool, "result": ...}."""
    data = json.dumps(params).encode("utf-8")
    request = urllib.request.Request(API.format(token=token, method=method), data=data, method="POST")
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        try:
            detail = json.loads(detail).get("description", detail)
        except ValueError:
            pass
        raise TelegramError(f"Telegram respondeu {error.code}: {detail[:200]}") from error
    except urllib.error.URLError as error:
        raise TelegramError(f"sem conexão com o Telegram: {error.reason}") from error
    if not payload.get("ok"):
        raise TelegramError(f"Telegram recusou {method}: {payload.get('description', '?')}")
    return payload.get("result", {})


class Bot:
    def __init__(self, token: str, chat_id: int, call=None):
        self.token = token
        self.chat_id = int(chat_id)
        self.offset = 0
        # Injetável nos testes: call(method, params) -> result
        self._call = call or (lambda method, params, timeout=40: http_call(self.token, method, params, timeout))

    # ---- saída --------------------------------------------------------------

    def send(self, reply: bridge.Reply, chat_id: int | None = None) -> dict:
        params: dict = {"chat_id": chat_id or self.chat_id, "text": reply.text}
        if reply.buttons:
            params["reply_markup"] = {"inline_keyboard": [[{"text": label, "callback_data": data}] for label, data in reply.buttons]}
        return self._call("sendMessage", params)

    def clear_buttons(self, message: dict) -> None:
        """Tira os botões de uma mensagem antiga depois que um deles foi usado."""
        chat = (message.get("chat") or {}).get("id")
        if chat is None or "message_id" not in message:
            return
        try:
            self._call("editMessageReplyMarkup", {"chat_id": chat, "message_id": message["message_id"], "reply_markup": {"inline_keyboard": []}})
        except TelegramError as error:
            log.debug("não limpei botões: %s", error)

    # ---- entrada ------------------------------------------------------------

    def poll(self, timeout: int = 25) -> list[dict]:
        params = {"timeout": timeout, "offset": self.offset, "allowed_updates": ["message", "callback_query"]}
        updates = self._call("getUpdates", params, timeout=timeout + 15) or []
        for update in updates:
            self.offset = max(self.offset, int(update.get("update_id", 0)) + 1)
        return updates

    def handle_update(self, update: dict) -> bridge.Reply | None:
        """Uma atualização vira, no máximo, uma resposta enviada. Devolve o que respondeu."""
        if "callback_query" in update:
            query = update["callback_query"]
            chat = ((query.get("message") or {}).get("chat") or {}).get("id")
            if chat != self.chat_id:
                return None
            reply = bridge.handle_callback(str(query.get("data", "")))
            try:
                self._call("answerCallbackQuery", {"callback_query_id": query.get("id"), "text": reply.text[:200]})
            except TelegramError as error:
                log.debug("answerCallbackQuery: %s", error)
            self.clear_buttons(query.get("message") or {})
            self.send(reply)
            return reply
        message = update.get("message")
        if not message:
            return None
        chat = (message.get("chat") or {}).get("id")
        if chat != self.chat_id:
            log.info("mensagem de chat desconhecido %s ignorada", chat)
            return None
        text = message.get("text")
        if not text:
            self.send(bridge.Reply("Só entendo texto por enquanto."))
            return None
        reply = bridge.handle_text(text)
        self.send(reply)
        return reply

    def serve_once(self, timeout: int = 25) -> int:
        """Uma rodada: espera mensagens até `timeout` segundos e responde todas."""
        handled = 0
        for update in self.poll(timeout):
            try:
                if self.handle_update(update) is not None:
                    handled += 1
            except TelegramError as error:
                log.warning("falha ao responder: %s", error)
        return handled


# ---------------------------------------------------------------------------
# Pareamento
# ---------------------------------------------------------------------------


def pair(token: str, timeout: int = 180, call=None) -> int:
    """Espera a primeira mensagem privada e devolve o id daquele chat."""
    bot = Bot(token, 0, call=call)
    me = bot._call("getMe", {})
    print(f"bot @{me.get('username', '?')} encontrado. Abra ele no Telegram e mande qualquer mensagem.")
    # Descarta o que já estava na fila para não parear com uma mensagem velha.
    for update in bot.poll(0):
        pass
    deadline = time.time() + timeout
    while time.time() < deadline:
        for update in bot.poll(20):
            message = update.get("message") or {}
            chat = message.get("chat") or {}
            if chat.get("type") == "private" and chat.get("id"):
                name = chat.get("first_name") or chat.get("username") or "você"
                bot.send(bridge.Reply(f"Pareado com {name}. Mande 'ajuda' para ver o que eu entendo."), chat_id=chat["id"])
                return int(chat["id"])
    raise TelegramError("ninguém mandou mensagem a tempo; rode o setup de novo")
