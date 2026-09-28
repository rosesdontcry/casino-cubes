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

ANY_PAIR_MIN_GAP защищает от вырожденного случая, когда пары идут
практически впритык (например run длиной 4 подряд может теоретически
дать вторую "пару"-событие сразу за первой, если бы мы не отслеживали
это через длину run, а не через "соседство"; тем не менее gap оставлен
настраиваемым на будущее).
"""

from core.pattern_base import BasePattern
from core.alert_bus import Alert, AlertRow
from core.round_history import RoundHistory


class PairChainPattern(BasePattern):
    key = "pair_chain"
    description = "Любая пара запускает ожидание любой следующей пары (на любом кубике)"

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
            # length > 2 — та же серия продолжается, новых событий не создаём
        else:
            state["value"] = value
            state["length"] = 1

    def _on_pair_detected(self, field_key: str, value: int, idx: int, history: RoundHistory) -> None:
        pair_start = idx - 1
        pair_end = idx

        if not self._chain["waiting"]:
            self._chain["waiting"] = True
            self._chain["start_idx"] = pair_start
            self._chain["last_pair_end_idx"] = pair_end
            return

        gap = pair_start - self._chain["last_pair_end_idx"] - 1
        if gap >= self._min_gap:
            self._publish_alert(field_key, value, self._chain["start_idx"], pair_end, history)
            self._chain["start_idx"] = pair_start
            self._chain["last_pair_end_idx"] = pair_end
        # иначе пара слишком близко к предыдущей — игнорируем, цепочка не обновляется

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
            title="НОВАЯ ПАРА!",
            subtitle_lines=[
                f"{label} — {value}",
                f"Длина цепочки: {len(rows)} раундов",
            ],
            rows=rows,
            separator="+",
        )
        self.alert_bus.publish(alert)