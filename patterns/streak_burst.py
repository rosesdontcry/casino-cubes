"""
Паттерн "всплеск последовательностей" (streak_burst).

Последовательностью считается run из 2+ одинаковых значений подряд на
ОДНОМ конкретном кубике. Засчитывается СРАЗУ в момент достижения длины 2
(не дожидаясь прерывания run) — дальнейшее удлинение той же серии
(3, 4, 5... подряд) не создаёт новых засчитываний.

Счётчик найденных последовательностей — ОБЩИЙ для обоих кубиков сразу.
Как только накопилось >= SEQ_COUNT_THRESHOLD последовательностей — алерт
со всеми найденными сериями и полный сброс счётчика.
"""

from core.pattern_base import BasePattern
from core.alert_bus import Alert, AlertRow
from core.round_history import RoundHistory


class StreakBurstPattern(BasePattern):
    key = "streak_burst"
    description = "Накопление N последовательностей (2+ подряд) на обоих кубиках суммарно"

    def __init__(self, alert_bus, tracked_fields: dict, threshold: int):
        super().__init__(alert_bus)
        self._fields = tracked_fields
        self._threshold = threshold

        self._run_state = {
            field: {"value": None, "length": 0, "start_idx": None}
            for field in tracked_fields
        }

        self._completed_sequences: list[dict] = []

    def on_round(self, idx: int, round_data: dict, history: RoundHistory) -> None:
        for field_key in self._fields:
            value = round_data[field_key]
            self._process_field(field_key, idx, value, history)

    def _process_field(self, field_key: str, idx: int, value: int, history: RoundHistory) -> None:
        state = self._run_state[field_key]

        if state["value"] == value:
            state["length"] += 1

            if state["length"] == 2:
                # серия только что образовалась — засчитываем сразу
                self._completed_sequences.append({
                    "field": field_key,
                    "value": value,
                    "start_idx": state["start_idx"],
                    "end_idx": idx,
                })

                if len(self._completed_sequences) >= self._threshold:
                    self._publish_alert(history)
                    self._completed_sequences = []

            # при length > 2 (та же серия продолжает расти) — ничего не делаем,
            # это НЕ новая последовательность
        else:
            state["value"] = value
            state["length"] = 1
            state["start_idx"] = idx

    def _publish_alert(self, history: RoundHistory) -> None:
        sequences = self._completed_sequences
        icons = {"dice1": "🔴", "dice2": "🔵"}

        full_start = min(s["start_idx"] for s in sequences)
        full_end = max(s["end_idx"] for s in sequences)

        marked_indices = set()
        for s in sequences:
            for i in range(s["start_idx"], s["end_idx"] + 1):
                marked_indices.add(i)

        summary = ", ".join(
            f"{icons.get(s['field'], '🎲')}{s['value']}{s['value']}" for s in sequences
        )

        rows = []
        for i in range(full_start, full_end + 1):
            round_data = history.get(i)
            if round_data is None:
                continue
            marker = "🔥" if i in marked_indices else "  "
            rows.append(AlertRow(round_data=round_data, marker=marker))

        alert = Alert(
            pattern_key=self.key,
            icon="🎲",
            title="МНОГО ПОСЛЕДОВАТЕЛЬНОСТЕЙ!",
            subtitle_lines=[
                f"Найдено: {len(sequences)}",
                summary,
            ],
            rows=rows,
            separator="~",
        )
        self.alert_bus.publish(alert)