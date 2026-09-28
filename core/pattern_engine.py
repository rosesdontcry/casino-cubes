"""
Движок обработки раундов: хранит историю и список паттернов,
на каждый новый раунд прогоняет его через всех подписчиков.
"""

from core.round_history import RoundHistory
from core.pattern_base import BasePattern


class PatternEngine:
    def __init__(self, history: RoundHistory, patterns: list[BasePattern]):
        self.history = history
        self.patterns = patterns

    def process_round(self, round_data: dict) -> int:
        idx = self.history.append(round_data)
        for pattern in self.patterns:
            pattern.on_round(idx, round_data, self.history)
        return idx