"""
Паттерн "симметричный разрыв" (symmetric_gap).

Если обозначить повтор значения на конкретном кубике как X, а любое
другое значение как O, паттерн ищет последовательности вида:

    x o^N x o^N x        (N от MIN_O_COUNT до MAX_O_COUNT)

Примеры при N=1: x o x  ->  5, _, 5   (xoxox без учёта промежуточных "o")
Примеры при N=2: x o o x o o x  ->  5, _, _, 5, _, _, 5

Реализация не хранит всю историю значений — только последние 2 индекса
появления каждого значения (1..6) на каждом отслеживаемом кубике.
Как только третье появление того же значения найдено, сравниваются два
промежутка между появлениями: если они равны и укладываются в диапазон
[MIN_O_COUNT, MAX_O_COUNT] — это и есть искомый паттерн.
"""

from core.pattern_base import BasePattern
from core.alert_bus import Alert, AlertRow
from core.round_history import RoundHistory


class SymmetricGapPattern(BasePattern):
    key = "symmetric_gap"
    description = "Симметричный повтор значения: x o^N x o^N x (N от MIN до MAX)"

    def __init__(self, alert_bus, tracked_fields: dict, min_o_count: int, max_o_count: int):
        super().__init__(alert_bus)
        self._fields = tracked_fields
        self._min_o = min_o_count
        self._max_o = max_o_count

        # occurrences[field][value] -> список последних (максимум 2) индексов появления
        self._occurrences = {
            field: {value: [] for value in range(1, 7)}
            for field in tracked_fields
        }

    def on_round(self, idx: int, round_data: dict, history: RoundHistory) -> None:
        for field_key in self._fields:
            value = round_data[field_key]
            occ = self._occurrences[field_key][value]

            if len(occ) >= 2:
                last1 = occ[-1]  # второе по счёту предыдущее появление (второй "x")
                last2 = occ[-2]  # появление до этого (первый "x")

                gap1 = idx - last1 - 1      # количество "o" между 2-м и 3-м x
                gap2 = last1 - last2 - 1    # количество "o" между 1-м и 2-м x

                if gap1 == gap2 and self._min_o <= gap1 <= self._max_o:
                    self._publish_alert(field_key, value, last2, last1, idx, gap1, history)

            occ.append(idx)
            if len(occ) > 2:
                occ.pop(0)  # держим только последние 2 вхождения — окно скользит

    def _publish_alert(self, field_key: str, value: int,
                        idx1: int, idx2: int, idx3: int, gap: int,
                        history: RoundHistory) -> None:
        label = self._fields[field_key]["label"]
        icon = {"dice1": "🔴", "dice2": "🔵"}.get(field_key, "🎲")
        pattern_shape = "x" + "o" * gap + "x" + "o" * gap + "x"

        rows = []
        for i in range(idx1, idx3 + 1):
            round_data = history.get(i)
            if round_data is None:
                continue
            marker = "🎯" if i in (idx1, idx2, idx3) else "  "
            rows.append(AlertRow(round_data=round_data, marker=marker))

        alert = Alert(
            pattern_key=self.key,
            icon=icon,
            title="XOX-ПАТТЕРН!",
            subtitle_lines=[
                f"{label} — {value}",
                f"Шаблон: {pattern_shape}",
            ],
            rows=rows,
            separator="#",
        )
        self.alert_bus.publish(alert)