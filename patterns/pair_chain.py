"""
Паттерн "цепочка любых пар" (pair_chain).

"Пара" — момент, когда run одинаковых значений на КОНКРЕТНОМ кубике
достигает длины ровно 2 (тройка 1,1,1 считается ОДНОЙ парой, а не двумя —
дальнейший рост той же серии не создаёт новых событий).

Как только образовалась первая пара (на любом кубике, любое значение) —
начинаем ждать. Между парами может быть сколько угодно "обычных" раундов.
Как только появляется ЛЮБАЯ следующая пара (неважно, то же значение или
нет, тот же кубик или нет) — публикуется алерт с диапазоном от первой до
второй пары, и вторая пара становится новым стартом ожидания.
"""

from core.pattern_base import BasePattern
from core.alert_bus import Alert, AlertRow
from core.round_history import RoundHistory


class PairChainPattern(BasePattern):
    key = "pair_chain"
    description = "Любая пара запускает ожидание любой следующей пары (на любом кубике)"

    _ICONS = {"dice1": "🔴", "dice2": "🔵"}

    def __init__(self, alert_bus, tracked_fields: dict, min_gap: int):
        super().__init__(alert_bus)
        self._fields = tracked_fields
        self._min_gap = min_gap

        self._run_state = {
            field: {"value": None, "length": 0}
            for field in tracked_fields
        }

        self._chain = {
            "waiting": False,
            "start_idx": None,
            "start_field": None,
            "start_value": None,
            "last_pair_end_idx": None,
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
        chain = self._chain

        if not chain["waiting"]:
            self._set_new_start(field_key, value, pair_start, pair_end)
            return

        gap = pair_start - chain["last_pair_end_idx"] - 1
        if gap >= self._min_gap:
            self._publish_alert(
                start_field=chain["start_field"],
                start_value=chain["start_value"],
                start_idx=chain["start_idx"],
                end_field=field_key,
                end_value=value,
                end_idx=pair_end,
                history=history,
            )
            self._set_new_start(field_key, value, pair_start, pair_end)
        # иначе пара слишком близко к предыдущей — игнорируем, цепочка не обновляется

    def _set_new_start(self, field_key: str, value: int, start_idx: int, end_idx: int) -> None:
        self._chain.update({
            "waiting": True,
            "start_idx": start_idx,
            "start_field": field_key,
            "start_value": value,
            "last_pair_end_idx": end_idx,
        })

    def _publish_alert(self, start_field: str, start_value: int, start_idx: int,
                        end_field: str, end_value: int, end_idx: int,
                        history: RoundHistory) -> None:
        start_icon = self._ICONS.get(start_field, "🎲")
        end_icon = self._ICONS.get(end_field, "🎲")

        rows = self._build_rows(start_idx, end_idx, history)

        alert = Alert(
            pattern_key=self.key,
            icon="🎲",
            title="ПАРА-ПРОПУСКИ-ПАРА",
            subtitle_lines=[
                f"{start_value}{start_icon}{start_value} ... {end_icon}{end_value}{end_value}",
                f"Длина: {len(rows)} раундов",
            ],
            rows=rows,
            separator="+",
        )
        self.alert_bus.publish(alert)

    def _build_rows(self, start_idx: int, end_idx: int, history: RoundHistory) -> list[AlertRow]:
        marked_indices = {start_idx, start_idx + 1, end_idx - 1, end_idx}

        rows = []
        for i in range(start_idx, end_idx + 1):
            round_data = history.get(i)
            if round_data is None:
                continue
            marker = "🔥" if i in marked_indices else "   "
            rows.append(AlertRow(round_data=round_data, marker=marker))

        return rows