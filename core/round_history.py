"""
Хранилище истории раундов с непрерывной (сквозной) индексацией.

Даже если в памяти хранится ограниченное окно (maxlen), индекс каждого
раунда — это его порядковый номер с начала работы бота (или с учётом
подгруженной истории из БД при старте). Это нужно, чтобы паттерны могли
ссылаться на индексы раундов и строить контекст вокруг найденных серий,
даже если сам раунд уже "вытолкнут" из скользящего окна.
"""

from collections import deque


class RoundHistory:
    def __init__(self, maxlen: int, initial_rounds: list | None = None):
        self._data = deque(maxlen=maxlen)
        self._total_rounds = 0

        if initial_rounds:
            for round_data in initial_rounds:
                self._data.append(round_data)
            # total_rounds отражает РЕАЛЬНОЕ количество раундов, которые "были",
            # даже если часть из них уже не поместилась в deque (maxlen меньше)
            self._total_rounds = len(initial_rounds)

    @property
    def total_rounds(self) -> int:
        return self._total_rounds

    def append(self, round_data: dict) -> int:
        """Добавляет новый раунд и возвращает его сквозной индекс."""
        idx = self._total_rounds
        self._data.append(round_data)
        self._total_rounds += 1
        return idx

    def get(self, idx: int) -> dict | None:
        """Возвращает раунд по сквозному индексу, либо None, если он уже выпал из окна."""
        offset = self._total_rounds - len(self._data)
        local_i = idx - offset
        if 0 <= local_i < len(self._data):
            return self._data[local_i]
        return None

    def get_range(self, start_idx: int, end_idx: int) -> list[dict]:
        """Возвращает список раундов в диапазоне [start_idx, end_idx], пропуская отсутствующие."""
        result = []
        for i in range(start_idx, end_idx + 1):
            r = self.get(i)
            if r is not None:
                result.append(r)
        return result

    def __len__(self) -> int:
        return len(self._data)