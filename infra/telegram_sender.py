"""
Транспортный слой для отправки сообщений в Telegram.

TelegramSender реализует протокол AlertSender (core/alert_bus.py) —
принимает логический bot_key и резолвит его в реальный токен через
config.BOT_TOKENS.

TelegramNotifier — более простая обёртка для остального кода проекта
(например, команд /stats, /export), которая работает с конкретным
токеном напрямую, минуя AlertBus.
"""

from infra.telegram_api import send_message, send_document

import config


class TelegramNotifier:
    """Прямая обёртка над конкретным ботом (токен + список чатов)."""

    def __init__(self, token: str, chat_ids: list[str]):
        self._token = token
        self._chat_ids = chat_ids

    def send(self, text: str) -> None:
        for chat_id in self._chat_ids:
            try:
                send_message(self._token, chat_id, text)
            except Exception as e:
                print(f"[Telegram] Ошибка отправки сообщения в чат {chat_id}: {e}")

    def send_document(self, filename: str, caption: str = "") -> None:
        for chat_id in self._chat_ids:
            try:
                send_document(self._token, chat_id, filename, caption)
            except Exception as e:
                print(f"[Telegram] Ошибка отправки файла в чат {chat_id}: {e}")


class TelegramSender:
    """Реализация AlertSender для AlertBus — резолвит bot_key -> TelegramNotifier."""

    def __init__(self, bot_tokens: dict[str, str], chat_ids: list[str]):
        self._notifiers = {
            bot_key: TelegramNotifier(token, chat_ids)
            for bot_key, token in bot_tokens.items()
        }

    def send(self, bot_key: str, text: str) -> None:
        notifier = self._notifiers.get(bot_key)
        if notifier is None:
            print(f"[TelegramSender] Неизвестный bot_key '{bot_key}', сообщение не отправлено")
            return
        notifier.send(text)


def build_default_sender() -> TelegramSender:
    """Фабрика для быстрой сборки сендера из конфигурации проекта."""
    return TelegramSender(config.BOT_TOKENS, config.TELEGRAM_CHAT_IDS)


def build_notifier(bot_key: str) -> TelegramNotifier:
    """Отдельный notifier для прямого использования вне AlertBus (например, команды бота)."""
    token = config.BOT_TOKENS[bot_key]
    return TelegramNotifier(token, config.TELEGRAM_CHAT_IDS)