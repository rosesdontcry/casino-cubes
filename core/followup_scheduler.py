"""
Простой планировщик отложенных вызовов, завязанных на индекс раунда,
а не на реальное время. Используется паттернами, которым нужно сделать
что-то ПОСЛЕ того, как пройдёт ещё N раундов с момента события
(например: паттерн сработал -> прислать доп. статистику через 2 раунда).

Планировщик не хранит ничего специфичного для конкретного паттерна —
он просто носит список (due_idx, callback) и вызывает callback(), когда
текущий idx достигает или превышает due_idx.
"""

from dataclasses import dataclass
from typing import Callable


@dataclass
class ScheduledTask:
    due_idx: int
    callback: Callable[[], None]


class FollowupScheduler:
    def __init__(self):
        self._tasks: list[ScheduledTask] = []

    def schedule(self, current_idx: int, delay: int, callback: Callable[[], None]) -> None:
        self._tasks.append(ScheduledTask(due_idx=current_idx + delay, callback=callback))

    def tick(self, current_idx: int) -> None:
        """Вызывать на каждый обработанный раунд — выполнит все задачи, чей срок настал."""
        ready = [t for t in self._tasks if current_idx >= t.due_idx]
        for task in ready:
            task.callback()
            self._tasks.remove(task)