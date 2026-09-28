"""
Паттерн "повтор конкретной пары" (repeating_pair).

"Пара" — момент, когда run одинаковых значений на КОНКРЕТНОМ кубике
достигает длины ровно 2 (см. pair_chain.py — та же семантика).

В отличие от pair_chain, здесь отслеживается не "любая следующая пара",
а именно ПОВТОР одной и той же цели: (поле, значение).

  - Первая пара становится целью ожидания.
  - Если следующая пара совпадает по полю и значению с целью — это
    зафиксированный повтор: публикуется алерт, и эта же пара становится
    новым стартом ожидания (цель остаётся прежней).
  - Если следующая пара НЕ совпадает с целью (другое значение и/или
    другое поле) — цель полностью меняется на эту новую пару, старое
    ожидание забывается без всякого уведомления.

PAIR_MIN_GAP защищает от вырожденного случая, когда рост той же серии
(например run длиной 3+) мог бы создать конфликт при засчитывании —
на практике, благодаря детекту "длина == 2", этого не происходит, но
gap оставлен настраиваемым на случай реальных наблюдений вроде описанных
ранее (см. историю обсуждения бага с "1,1,1").
"""

from core.pattern_base import BasePattern
from core.alert_bus import Alert, AlertRow
from core.round_history import RoundHistory


class RepeatingPairPattern(BasePattern):
    key = "repeating_pair"
    description = "Пара -> ждём повтор ТОЙ ЖЕ пары; любая другая пара сбивает цель"

    def __init__(self, alert_bus, tracked_fields: dict, min_gap: int):
        super().__init__(alert_bus)
        self._fields = tracked_fields
        self._min_gap = min_gap

        self._run_state = {
            field: {"value": None, "length": 0}
            for field in tracked_fields
        }

        self._target = {
            "waiting": False,
            "field": None,
            "value": None,
            "start_idx": None,
            "last_event_end_idx": None,
        }

    def on_round(self, idx: int, round_data: dict, history: RoundHistory) -> None:
        for field_key in self._fields:
            value = round_data[field_key]
            self._process_field(field_key, idx, value, history)

    def _process_field(self, field_key: str, idx: int, value: int, history: RoundHistory) -> None:
        state = self._run_state[field_key]

        if state["value"] == value:
            state["length"] += 1
            if state["length"] == 2:
                self._on_pair_detected(field_key, value, idx, history)
        else:
            state["value"] = value
            state["length"] = 1

    def _on_pair_detected(self, field_key: str, value: int, idx: int, history: RoundHistory) -> None:
        pair_start = idx - 1
        pair_end = idx
        target = self._target

        if not target["waiting"]:
            self._set_new_target(field_key, value, pair_start, pair_end)
            return

        is_same_target = (field_key == target["field"] and value == target["value"])

        if is_same_target:
            gap = pair_start - target["last_event_end_idx"] - 1
            if gap >= self._min_gap:
                self._publish_alert(field_key, value, target["start_idx"], pair_end, history)
                self._set_new_target(field_key, value, pair_start, pair_end)
            # иначе слишком близко к предыдущему событию — игнорируем, цель не меняется
        else:
            # другая пара — полностью перебивает цель, без уведомления
            self._set_new_target(field_key, value, pair_start, pair_end)

    def _set_new_target(self, field_key: str, value: int, start_idx: int, end_idx: int) -> None:
        self._target.update({
            "waiting": True,
            "field": field_key,
            "value": value,
            "start_idx": start_idx,
            "last_event_end_idx": end_idx,
        })

    def _publish_alert(self, field_key: str, value: int,
                        start_idx: int, end_idx: int, history: RoundHistory) -> None:
        label = self._fields[field_key]["label"]
        icon = {"dice1": "🔴", "dice2": "🔵"}.get(field_key, "🎲")

        rows = [
            AlertRow(round_data=r)
            for r in history.get_range(start_idx, end_idx)
        ]

        alert = Alert(
            pattern_key=self.key,
            icon=icon,
            title="ПОВТОР ПАРЫ!",
            subtitle_lines=[
                f"{label} — {value}",
                f"Длина серии: {len(rows)} раундов",
            ],
            rows=rows,
            separator="=",
        )
        self.alert_bus.publish(alert)