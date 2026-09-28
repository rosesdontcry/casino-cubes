"""
Единая точка публикации алертов от паттернов.

Паттерны не знают ничего про Telegram, токены ботов или лимиты сообщений —
они просто собирают Alert (шапка + список строк с маркерами) и вызывают
bus.publish(alert). Дальше AlertBus сам решает:
  - как это красиво напечатать в консоль (единый визуальный стиль);
  - как это разбить на части, если текст слишком длинный для Telegram;
  - в какой бот отправить (по ключу паттерна через routing-таблицу).

Реальная отправка (HTTP-запросы в Telegram) вынесена за пределы core —
сюда передаётся только объект, реализующий протокол AlertSender.
"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class AlertRow:
    round_data: dict
    marker: str = "  "


@dataclass
class Alert:
    pattern_key: str                       # технический ключ паттерна, для роутинга
    icon: str                              # emoji в шапке (обычно цвет кубика или 🎲)
    title: str                             # например "ПАТТЕРН!", "ПОВТОР ПАРЫ!"
    subtitle_lines: list[str] = field(default_factory=list)  # доп. строки жирным в шапке
    rows: list[AlertRow] = field(default_factory=list)
    separator: str = "─"                   # символ рамки для консольного вывода


class AlertSender(Protocol):
    """Абстракция транспорта. Реализуется в infra-слое (см. infra/telegram_sender.py)."""

    def send(self, bot_key: str, text: str) -> None: ...


class AlertBus:
    def __init__(self, routing: dict[str, str], sender: AlertSender, max_len: int = 3500):
        self._routing = routing  # pattern_key -> bot_key
        self._sender = sender
        self._max_len = max_len

    def publish(self, alert: Alert) -> None:
        self._print_console(alert)

        bot_key = self._routing.get(alert.pattern_key)
        if bot_key is None:
            print(f"[AlertBus] Нет маршрута для паттерна '{alert.pattern_key}', "
                  f"уведомление не отправлено")
            return

        chunks = self._render_telegram_chunks(alert)
        total = len(chunks)
        for i, chunk in enumerate(chunks):
            prefix = f"(часть {i + 1}/{total})\n" if total > 1 else ""
            self._sender.send(bot_key, prefix + chunk)

    # ------------------------------------------------------------------
    # Рендеринг — чистые функции без побочных эффектов (кроме print)
    # ------------------------------------------------------------------

    def _print_console(self, alert: Alert) -> None:
        width = 34
        print()
        print(f"  {alert.separator * width}")
        print(f"  {alert.icon} {alert.title}")
        for line in alert.subtitle_lines:
            print(f"  {line}")
        print(f"  {alert.separator * width}")
        for row in alert.rows:
            r = row.round_data
            print(f"  {row.marker} [{r['round_public_id']}]  🔴{r['dice1']}  vs  {r['dice2']}🔵")
        print(f"  {alert.separator * width}")
        print()

    def _render_telegram_chunks(self, alert: Alert) -> list[str]:
        header = f"{alert.icon} <b>{alert.title}</b>\n"
        for line in alert.subtitle_lines:
            header += f"<b>{line}</b>\n"

        lines = [
            f"{row.marker} [{row.round_data['round_public_id']}]  "
            f"{row.round_data['dice1']} vs {row.round_data['dice2']}\n"
            for row in alert.rows
        ]

        if not lines:
            return [header]

        chunks = []
        current = header + "<pre>"
        for line in lines:
            if len(current) + len(line) + len("</pre>") > self._max_len:
                chunks.append(current + "</pre>")
                current = "<pre>"
            current += line
        chunks.append(current + "</pre>")
        return chunks