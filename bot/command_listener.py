"""
Long-polling слушатель команд Telegram (/export, /stats и т.д.).

Ключевой момент, исправляющий старую проблему с 409 Conflict:
offset хранится ВНУТРИ бесконечного цикла listen(), а не пересоздаётся
при каждом внешнем перезапуске — до тех пор, пока сам процесс жив,
Telegram не увидит "двух одновременных" getUpdates с одним токеном.
"""

import time

from infra.telegram_api import get_updates, delete_webhook

RECONNECT_DELAY = 15  # должен быть больше, чем timeout внутри get_updates (иначе гонка -> 409)


def listen(token: str, allowed_chat_ids: list[str], handle_command) -> None:
    """
    handle_command(chat_id: str, text: str) -> None — обработчик команды,
    вызывается для каждого входящего текстового сообщения от разрешённого чата.
    """
    try:
        delete_webhook(token, drop_pending_updates=True)
    except Exception as e:
        print(f"[CommandListener] Не удалось снять вебхук: {e}")

    offset = 0

    while True:
        try:
            data = get_updates(token, offset, timeout=25)
        except Exception as e:
            print(f"[CommandListener] Сетевая ошибка: {e}. Повтор через {RECONNECT_DELAY} сек.")
            time.sleep(RECONNECT_DELAY)
            continue

        for update in data.get("result", []):
            offset = update["update_id"] + 1

            message = update.get("message") or update.get("edited_message")
            if not message:
                continue

            chat_id = str(message.get("chat", {}).get("id"))
            text = message.get("text")

            if text is None:
                continue

            if allowed_chat_ids and chat_id not in allowed_chat_ids:
                continue

            try:
                handle_command(chat_id, text)
            except Exception as e:
                print(f"[CommandListener] Ошибка обработки команды '{text}': {e}")


def run_forever_safe(token: str, allowed_chat_ids: list[str], handle_command) -> None:
    """Внешняя защита от полного падения потока — но offset всё равно живёт внутри listen()."""
    while True:
        try:
            listen(token, allowed_chat_ids, handle_command)
        except Exception as e:
            print(f"[CommandListener] Поток упал: {e}. Полный перезапуск через {RECONNECT_DELAY} сек.")
        time.sleep(RECONNECT_DELAY)