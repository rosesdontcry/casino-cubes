"""
Паттерн "всплеск последовательностей" (streak_burst).

Последовательностью считается run из 2+ одинаковых значений подряд на
ОДНОМ конкретном кубике. Засчитывается СРАЗУ в момент достижения длины 2
(не дожидаясь прерывания run). Если та же серия продолжает расти дальше
(3, 4, 5... подряд) — это НЕ создаёт новых засчитываний, но итоговая
длина серии запоминается и используется при отображении в уведомлении
(например "6666" для четырёх шестёрок подряд, а не всегда "66").

ВАЖНО: пулы последовательностей ведутся ОТДЕЛЬНО для каждого кубика.
Это значит, что один "всплеск" всегда состоит из серий ОДНОГО цвета —
например 🔴11, 🔴22, 🔴33, но никогда не смешивает 🔴 и 🔵 в одном
уведомлении. Каждый кубик копит свой собственный пул и проверяет свой
собственный разрыв (см. STREAK_BURST_MAX_GAP) независимо от другого.

Если между окончанием предыдущей учтённой серии и началом новой (в рамках
ОДНОГО И ТОГО ЖЕ кубика) проходит слишком много "обычных" раундов —
накопленный пул этого кубика сбрасывается, и отсчёт начинается заново
именно с этой новой серии.

Как только пул конкретного кубика накопил >= SEQ_COUNT_THRESHOLD
последовательностей — алерт со всеми найденными сериями ЭТОГО кубика,
и полный сброс пула именно этого кубика (пул другого кубика не трогается).
"""

from core.pattern_base import BasePattern
from core.alert_bus import Alert, AlertRow
from core.round_history import RoundHistory


class StreakBurstPattern(BasePattern):
    key = "streak_burst"
    description = "Накопление N последовательностей (2+ подряд) ОДНОГО цвета, идущих без больших пропусков"

    _ICONS = {"dice1": "🔴", "dice2": "🔵"}

    def __init__(self, alert_bus, tracked_fields: dict, threshold: int, max_gap: int):
        super().__init__(alert_bus)
        self._fields = tracked_fields
        self._threshold = threshold
        self._max_gap = max_gap

        self._run_state = {
            field: {"value": None, "length": 0, "active_seq": None}
            for field in tracked_fields
        }

        # у каждого кубика СВОЙ пул и СВОЯ отметка последней активности —
        # они никогда не смешиваются между собой
        self._pools: dict[str, list[dict]] = {field: [] for field in tracked_fields}
        self._last_activity_idx: dict[str, int | None] = {field: None for field in tracked_fields}

    def on_round(self, idx: int, round_data: dict, history: RoundHistory) -> None:
        for field_key in self._fields:
            value = round_data[field_key]
            self._process_field(field_key, idx, value, history)

    def _process_field(self, field_key: str, idx: int, value: int, history: RoundHistory) -> None:
        state = self._run_state[field_key]

        if state["value"] == value:
            state["length"] += 1

            if state["length"] == 2:
                self._start_new_sequence(field_key, value, idx, state, history)
            elif state["active_seq"] is not None:
                # серия продолжает расти — обновляем итоговую границу для
                # корректного отображения длины, но НЕ создаём новое событие
                state["active_seq"]["end_idx"] = idx
                self._last_activity_idx[field_key] = idx
        else:
            state["value"] = value
            state["length"] = 1
            state["active_seq"] = None

    def _start_new_sequence(self, field_key: str, value: int, idx: int,
                             state: dict, history: RoundHistory) -> None:
        seq_start_idx = idx - 1
        seq_end_idx = idx

        last_idx = self._last_activity_idx[field_key]
        if last_idx is not None:
            gap = seq_start_idx - last_idx - 1
            if gap > self._max_gap:
                self._pools[field_key] = []  # разрыв слишком большой — пул ЭТОГО кубика отбрасывается

        sequence = {
            "field": field_key,
            "value": value,
            "start_idx": seq_start_idx,
            "end_idx": seq_end_idx,
        }
        self._pools[field_key].append(sequence)
        state["active_seq"] = sequence
        self._last_activity_idx[field_key] = seq_end_idx

        if len(self._pools[field_key]) >= self._threshold:
            self._publish_alert(field_key, history)
            self._pools[field_key] = []
            # сбрасываем активную ссылку ТОЛЬКО у этого кубика — другой кубик не трогаем
            self._run_state[field_key]["active_seq"] = None

    def _publish_alert(self, field_key: str, history: RoundHistory) -> None:
        sequences = self._pools[field_key]
        icon = self._ICONS.get(field_key, "🎲")
        label = self._fields[field_key]["label"]

        full_start = min(s["start_idx"] for s in sequences)
        full_end = max(s["end_idx"] for s in sequences)

        marked_indices = set()
        for s in sequences:
            for i in range(s["start_idx"], s["end_idx"] + 1):
                marked_indices.add(i)

        summary = ", ".join(
            f"{icon}{str(s['value']) * (s['end_idx'] - s['start_idx'] + 1)}"
            for s in sequences
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
            icon=icon,
            title="МНОГО ПОСЛЕДОВАТЕЛЬНОСТЕЙ!",
            subtitle_lines=[
                f"{label}",
                f"Найдено: {len(sequences)} ({summary})",
            ],
            rows=rows,
            separator="~",
        )
        self.alert_bus.publish(alert)