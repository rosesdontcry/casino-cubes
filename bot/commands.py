"""
Обработчик входящих команд Telegram (/export, /stats, /help).

handle_command получает готовые зависимости через замыкание (build_command_handler),
а не через глобальные переменные — это позволяет тестировать логику отдельно
от реального Telegram-транспорта.
"""

import re

import config
from infra.database import RoundsDatabase
from infra.telegram_sender import TelegramNotifier


def build_command_handler(db: RoundsDatabase, notifier: TelegramNotifier):
    def handle_command(chat_id: str, text: str) -> None:
        text = text.strip()

        if text.startswith("/export"):
            _handle_export(text, db, notifier)
        elif text.startswith("/stats"):
            _handle_stats(db, notifier)
        elif text.startswith("/help") or text.startswith("/start"):
            _handle_help(notifier)

    return handle_command


def _handle_export(text: str, db: RoundsDatabase, notifier: TelegramNotifier) -> None:
    match = re.match(r"/export\s*(\d+)?", text)
    limit = int(match.group(1)) if match and match.group(1) else config.EXPORT_LIMIT

    count = db.export_to_excel(limit=limit, filename=config.EXPORT_PATH)
    if count > 0:
        notifier.send_document(config.EXPORT_PATH, caption=f"📊 Экспорт последних {count} раундов")
    else:
        notifier.send("⚠️ Не удалось выполнить экспорт (данных нет или ошибка).")


def _handle_stats(db: RoundsDatabase, notifier: TelegramNotifier) -> None:
    total = db.count()
    notifier.send(f"📈 Всего сохранено раундов в базе: <b>{total}</b>")


def _handle_help(notifier: TelegramNotifier) -> None:
    notifier.send(
        "🤖 Доступные команды:\n"
        "/export [N] — выгрузить последние N раундов в Excel\n"
        "/stats — общее количество сохранённых раундов"
    )