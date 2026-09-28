"""
Базовый интерфейс для всех паттернов.

Любой новый паттерн — это класс, наследующий BasePattern и реализующий
on_round(). Паттерн сам решает, когда собрать Alert и опубликовать его
через alert_bus.publish(...). Никакой другой код трогать не нужно —
достаточно добавить паттерн в список при сборке PatternEngine в main.py.
"""

from abc import ABC, abstractmethod

from core.round_history import RoundHistory
from core.alert_bus import AlertBus


class BasePattern(ABC):
    key: str = "base_pattern"          # технический ключ — используется в routing AlertBus
    description: str = ""              # человекочитаемое описание паттерна

    def __init__(self, alert_bus: AlertBus):
        self.alert_bus = alert_bus

    @abstractmethod
    def on_round(self, idx: int, round_data: dict, history: RoundHistory) -> None:
        """Вызывается для каждого нового обработанного раунда."""
        raise NotImplementedError