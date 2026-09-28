"""
Низкоуровневый клиент Telegram Bot API (через прокси-воркер).

Здесь нет никакой бизнес-логики (роутинга ботов, форматирования алертов) —
только тонкая обёртка над HTTP-запросами. Всё остальное строится поверх
этого модуля (telegram_sender.py для алертов, command_listener.py для
входящих команд).
"""

import requests

TELEGRAM_API_BASE = "https://my-tg-proxy.iwantbunnygirl.workers.dev"

DEFAULT_TIMEOUT = 15


def _api_url(token: str, method: str) -> str:
    return f"{TELEGRAM_API_BASE}/bot{token}/{method}"


def send_message(token: str, chat_id: str, text: str, parse_mode: str = "HTML") -> dict:
    url = _api_url(token, "sendMessage")
    resp = requests.post(
        url,
        json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def send_document(token: str, chat_id: str, filename: str, caption: str = "") -> dict:
    url = _api_url(token, "sendDocument")
    with open(filename, "rb") as f:
        files = {"document": f}
        data = {"chat_id": chat_id, "caption": caption}
        resp = requests.post(url, data=data, files=files, timeout=60)
    resp.raise_for_status()
    return resp.json()


def get_updates(token: str, offset: int, timeout: int = 25) -> dict:
    url = _api_url(token, "getUpdates")
    resp = requests.get(
        url,
        params={"offset": offset, "timeout": timeout},
        timeout=timeout + 10,  # запас, чтобы наш клиент не отваливался раньше, чем ответит Telegram
    )
    resp.raise_for_status()
    return resp.json()


def delete_webhook(token: str, drop_pending_updates: bool = True) -> dict:
    """
    Обязательно вызывать перед стартом long-polling (getUpdates) — если для
    бота когда-либо настраивался вебхук, Telegram будет отвечать 409 Conflict
    на getUpdates, пока вебхук явно не снят.
    """
    url = _api_url(token, "deleteWebhook")
    resp = requests.get(
        url,
        params={"drop_pending_updates": str(drop_pending_updates).lower()},
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()