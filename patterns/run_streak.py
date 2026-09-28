"""
Паттерн "N подряд (+ опциональные пропуски и повтор)" (run_streak).

Конфигурация задаётся списком описаний вида:
    {"name": "triple", "icon": "", "desc": "четыре подряд подряд",
     "run_len": 4, "skips": 0, "matches": 0}

Логика состояния-машины для каждого (поле, описание паттерна):

    counting -> [skipping] -> [waiting_match]

  1. counting: копим run одинаковых значений на конкретном кубике.
     Как только длина run достигла run_len:
       - если skips == 0 и matches == 0 -> это "чистый" паттерн
         (например "N подряд") -> алерт сразу, состояние сбрасывается
         в counting с новым отсчётом от текущего значения.
       - иначе -> переходим в skipping.

  2. skipping: пропускаем ровно `skips` следующих раундов (любые
     значения допустимы), затем переходим в waiting_match.

  3. waiting_match: ждём `matches` раундов подряд с тем же значением,
     что было у исходного run. Если совпадение — засчитываем; если все
     `matches` совпадений найдены — алерт и followup-заявка, состояние
     возвращается в counting (новый отсчёт начинается с только что
     увиденного значения). Если совпадение НЕ произошло — состояние
     сбрасывается в counting, run начинается заново с текущего значения.

После публикации основного алерта паттерн регистрирует в собственном
FollowupScheduler отложенную задачу: через FOLLOWUP_AFTER раундов после
завершения паттерна прислать вторую, "статистическую" публикацию с тем
же диапазоном + несколько раундов, случившихся после.
"""

from core.pattern_base import BasePattern
from core.alert_bus import Alert, AlertRow
from core.round_history import RoundHistory
from core.followup_scheduler import FollowupScheduler


def _make_initial_state():
    return {
        "mode": "counting",  # counting -> skipping -> waiting_match
        "run_value": None,
        "run_length": 0,
        "run_start_idx": None,
        "run_end_idx": None,
        "skip_remaining": 0,
        "skip_indices": [],
        "match_remaining": 0,
        "match_indices": [],
    }


class RunStreakPattern(BasePattern):
    key = "run_streak"
    description = "N одинаковых подряд, опционально с пропуском и последующим повтором"

    def __init__(self, alert_bus, tracked_fields: dict, pattern_defs: list[dict],
                 context_before: int, followup_after: int):
        super().__init__(alert_bus)
        self._fields = tracked_fields
        self._pattern_defs = pattern_defs
        self._context_before = context_before
        self._followup_after = followup_after

        self._scheduler = FollowupScheduler()

        # state[field][pattern_name] -> состояние своей state-machine
        self._state = {
            field: {p["name"]: _make_initial_state() for p in pattern_defs}
            for field in tracked_fields
        }

    def on_round(self, idx: int, round_data: dict, history: RoundHistory) -> None:
        # сначала проверяем отложенные followup-задачи (они могли "созреть" именно на этом раунде)
        self._scheduler.tick(idx)

        for field_key in self._fields:
            value = round_data[field_key]
            for pattern_def in self._pattern_defs:
                state = self._state[field_key][pattern_def["name"]]
                self._process(field_key, pattern_def, idx, value, state, history)

    # ------------------------------------------------------------------
    # Основная state-machine
    # ------------------------------------------------------------------

    def _process(self, field_key: str, pattern_def: dict, idx: int, value: int,
                 state: dict, history: RoundHistory) -> None:
        target_len = pattern_def["run_len"]
        skip_count = pattern_def["skips"]
        match_count = pattern_def["matches"]

        if state["mode"] == "counting":
            self._handle_counting(field_key, pattern_def, idx, value, state,
                                   target_len, skip_count, match_count, history)

        elif state["mode"] == "skipping":
            state["skip_indices"].append(idx)
            state["skip_remaining"] -= 1
            if state["skip_remaining"] == 0:
                state["mode"] = "waiting_match"

        elif state["mode"] == "waiting_match":
            self._handle_waiting_match(field_key, pattern_def, idx, value, state, history)

    def _handle_counting(self, field_key, pattern_def, idx, value, state,
                          target_len, skip_count, match_count, history) -> None:
        if state["run_value"] == value:
            state["run_length"] += 1
        else:
            state["run_value"] = value
            state["run_length"] = 1
            state["run_start_idx"] = idx

        if state["run_length"] != target_len:
            return

        run_end_idx = idx

        if skip_count == 0 and match_count == 0:
            self._publish_and_schedule(
                field_key, pattern_def, state["run_value"],
                state["run_start_idx"], run_end_idx, [], [],
                history,
            )
            state["mode"] = "counting"
            state["run_value"] = None
            state["run_length"] = 0
            state["run_start_idx"] = None
        else:
            state["mode"] = "skipping"
            state["run_end_idx"] = run_end_idx
            state["skip_remaining"] = skip_count
            state["skip_indices"] = []
            state["match_remaining"] = match_count
            state["match_indices"] = []

    def _handle_waiting_match(self, field_key, pattern_def, idx, value, state, history) -> None:
        if value == state["run_value"]:
            state["match_indices"].append(idx)
            state["match_remaining"] -= 1
            if state["match_remaining"] == 0:
                self._publish_and_schedule(
                    field_key, pattern_def, state["run_value"],
                    state["run_start_idx"], state["run_end_idx"],
                    state["skip_indices"], state["match_indices"],
                    history,
                )
                state["mode"] = "counting"
                state["run_value"] = value
                state["run_length"] = 1
                state["run_start_idx"] = idx
        else:
            state["mode"] = "counting"
            state["run_value"] = value
            state["run_length"] = 1
            state["run_start_idx"] = idx

    # ------------------------------------------------------------------
    # Публикация алерта + постановка followup-задачи
    # ------------------------------------------------------------------

    def _publish_and_schedule(self, field_key: str, pattern_def: dict, target_value: int,
                               run_start_idx: int, run_end_idx: int,
                               skip_indices: list[int], match_indices: list[int],
                               history: RoundHistory) -> None:
        self._publish_main_alert(
            field_key, pattern_def, target_value,
            run_start_idx, run_end_idx, skip_indices, match_indices,
            history,
        )

        completion_idx = max([run_end_idx] + skip_indices + match_indices)

        self._scheduler.schedule(
            current_idx=completion_idx,
            delay=self._followup_after,
            callback=lambda: self._publish_followup_alert(
                field_key, pattern_def, target_value,
                run_start_idx, completion_idx, history,
            ),
        )

    def _publish_main_alert(self, field_key: str, pattern_def: dict, target_value: int,
                             run_start_idx: int, run_end_idx: int,
                             skip_indices: list[int], match_indices: list[int],
                             history: RoundHistory) -> None:
        label = self._fields[field_key]["label"]
        icon = {"dice1": "🔴", "dice2": "🔵"}.get(field_key, "🎲")

        rows = self._build_context_rows(
            run_start_idx, run_end_idx, skip_indices, match_indices, history,
        )

        alert = Alert(
            pattern_key=self.key,
            icon=icon,
            title="ПАТТЕРН!",
            subtitle_lines=[
                f"{label} — {target_value}",
                pattern_def["desc"],
            ],
            rows=rows,
            separator="─",
        )
        self.alert_bus.publish(alert)

    def _publish_followup_alert(self, field_key: str, pattern_def: dict, target_value: int,
                                 run_start_idx: int, completion_idx: int,
                                 history: RoundHistory) -> None:
        label = self._fields[field_key]["label"]

        extra_after = [completion_idx + 1, completion_idx + 2]
        # используем те же категории, что и в основном алерте, плюс "after"
        rows = self._build_context_rows(
            run_start_idx, completion_idx, [], [], history,
            extra_after_indices=extra_after,
        )

        alert = Alert(
            pattern_key=self.key,
            icon="📊",
            title="СТАТИСТИКА!",
            subtitle_lines=[
                f"{label} — {target_value}",
                pattern_def["desc"],
            ],
            rows=rows,
            separator="·",
        )
        self.alert_bus.publish(alert)

    # ------------------------------------------------------------------
    # Построение контекстных строк (before / run / skip / match / after)
    # ------------------------------------------------------------------

    def _build_context_rows(self, run_start_idx: int, run_end_idx: int,
                             skip_indices: list[int], match_indices: list[int],
                             history: RoundHistory,
                             extra_after_indices: list[int] | None = None) -> list[AlertRow]:
        categories: dict[int, str] = {}

        for i in range(run_start_idx, run_end_idx + 1):
            categories[i] = "run"
        for i in skip_indices:
            categories[i] = "skip"
        for i in match_indices:
            categories[i] = "match"

        before_start = run_start_idx - self._context_before
        for i in range(before_start, run_start_idx):
            categories.setdefault(i, "before")

        all_indices = [run_end_idx] + skip_indices + match_indices
        pattern_end = max(all_indices)

        full_end = pattern_end
        if extra_after_indices:
            for i in extra_after_indices:
                categories[i] = "after"
            full_end = max(pattern_end, max(extra_after_indices))

        markers = {"before": "⬅️", "run": "🔥", "skip": "⏭️", "match": "🔥", "after": "🆕"}

        rows = []
        for i in range(before_start, full_end + 1):
            round_data = history.get(i)
            if round_data is None:
                continue
            marker = markers.get(categories.get(i), "  ")
            rows.append(AlertRow(round_data=round_data, marker=marker))

        return rows