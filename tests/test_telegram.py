"""Testes do canal Telegram com uma API falsa: nada sai para a rede."""

import json
import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import agenda_store as store  # noqa: E402
import agenda_telegram as telegram  # noqa: E402

CHAT = 4242


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENDA_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("AGENDA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("AGENDA_NO_KEYRING", "1")
    monkeypatch.setenv("AGENDA_NO_NOTIFY", "1")


class FakeApi:
    def __init__(self, updates=None):
        self.updates = list(updates or [])
        self.calls = []

    def __call__(self, method, params, timeout=40):
        self.calls.append((method, params))
        if method == "getUpdates":
            pending, self.updates = self.updates, []
            return pending
        if method == "getMe":
            return {"username": "agenda_bot"}
        return {"message_id": len(self.calls), "chat": {"id": params.get("chat_id")}}


def message(text, chat=CHAT, update_id=1):
    return {"update_id": update_id, "message": {"message_id": 10, "chat": {"id": chat, "type": "private"}, "text": text}}


def test_mensagem_do_chat_pareado_vira_tarefa_e_resposta_com_botao():
    api = FakeApi([message("pagar luz amanhã")])
    bot = telegram.Bot("tok", CHAT, call=api)
    assert bot.serve_once(timeout=0) == 1
    assert bot.offset == 2
    task = store.read_state()["tasks"][0]
    sent = [p for m, p in api.calls if m == "sendMessage"]
    assert len(sent) == 1
    assert sent[0]["chat_id"] == CHAT
    assert sent[0]["text"].startswith("✓ Tarefa")
    assert sent[0]["reply_markup"] == {"inline_keyboard": [[{"text": "Desfazer", "callback_data": f"undo:task:{task['id']}"}]]}


def test_chat_desconhecido_e_ignorado():
    api = FakeApi([message("apaga tudo", chat=999)])
    bot = telegram.Bot("tok", CHAT, call=api)
    assert bot.serve_once(timeout=0) == 0
    assert store.read_state()["tasks"] == []
    assert not [m for m, _ in api.calls if m == "sendMessage"]


def test_clique_no_botao_desfaz_responde_e_limpa_os_botoes():
    api = FakeApi([message("comprar leite")])
    bot = telegram.Bot("tok", CHAT, call=api)
    bot.serve_once(timeout=0)
    task_id = store.read_state()["tasks"][0]["id"]
    api.updates = [{"update_id": 7, "callback_query": {"id": "cb1", "data": f"undo:task:{task_id}",
                                                       "message": {"message_id": 55, "chat": {"id": CHAT}}}}]
    assert bot.serve_once(timeout=0) == 1
    assert store.read_state()["tasks"] == []
    methods = [m for m, _ in api.calls]
    assert "answerCallbackQuery" in methods and "editMessageReplyMarkup" in methods
    cleared = next(p for m, p in api.calls if m == "editMessageReplyMarkup")
    assert cleared == {"chat_id": CHAT, "message_id": 55, "reply_markup": {"inline_keyboard": []}}
    assert api.calls[-1][1]["text"] == "✗ Desfeito: comprar leite"


def test_mensagem_sem_texto_recebe_aviso():
    api = FakeApi([{"update_id": 3, "message": {"message_id": 1, "chat": {"id": CHAT, "type": "private"}, "photo": []}}])
    bot = telegram.Bot("tok", CHAT, call=api)
    bot.serve_once(timeout=0)
    assert api.calls[-1][1]["text"] == "Só entendo texto por enquanto."


def test_pareamento_pega_o_primeiro_chat_privado_e_ignora_a_fila_velha():
    api = FakeApi()
    # A primeira chamada (descarte da fila) e a segunda (espera) vêm da mesma lista falsa,
    # então a mensagem antiga é consumida no descarte e a nova chega depois.
    api.updates = [message("velha", chat=1, update_id=1)]
    original_poll = telegram.Bot.poll

    def poll(self, timeout=25):
        updates = original_poll(self, timeout)
        if timeout == 0:
            api.updates = [message("oi", chat=CHAT, update_id=2)]
        return updates

    telegram.Bot.poll = poll
    try:
        assert telegram.pair("tok", timeout=5, call=api) == CHAT
    finally:
        telegram.Bot.poll = original_poll
    greeting = [p for m, p in api.calls if m == "sendMessage"][-1]
    assert greeting["chat_id"] == CHAT and greeting["text"].startswith("Pareado")


def test_credenciais_ficam_so_com_o_dono():
    assert telegram.load_credentials() is None
    assert telegram.is_configured() is False
    path = telegram.save_credentials("123:abc", CHAT)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert telegram.load_credentials() == {"token": "123:abc", "chat_id": CHAT}
    assert telegram.is_configured() is True
    assert json.load(open(path, encoding="utf-8"))["token"] == "123:abc"
