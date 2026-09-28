"""
Точка входа приложения.

Собирает все слои воедино:
  - infra: база данных, Telegram-транспорт, SSE-стрим
  - core: история раундов, AlertBus, движок паттернов
  - patterns: все зарегистрированные паттерны
  - bot: обработчик входящих команд

Порядок паттернов в списке не важен — они полностью независимы друг от друга.
"""

import threading

import config
from infra.database import RoundsDatabase
from infra.telegram_sender import build_default_sender, build_notifier
from infra.stream_client import listen_stream
from core.round_history import RoundHistory
from core.alert_bus import AlertBus
from core.pattern_engine import PatternEngine
from bot.command_listener import run_forever_safe
from bot.commands import build_command_handler

from patterns.run_streak import RunStreakPattern
from patterns.repeating_pair import RepeatingPairPattern
from patterns.symmetric_gap import SymmetricGapPattern
from patterns.streak_burst import StreakBurstPattern
from patterns.pair_chain import PairChainPattern


def build_engine(alert_bus: AlertBus, history: RoundHistory) -> PatternEngine:
    patterns = [
        RunStreakPattern(
            alert_bus, config.TRACKED_FIELDS, config.RUN_SKIP_MATCH_PATTERNS,
            config.CONTEXT_BEFORE, config.FOLLOWUP_AFTER,
        ),
        RepeatingPairPattern(
            alert_bus, config.TRACKED_FIELDS, config.PAIR_MIN_GAP,
        ),
        SymmetricGapPattern(
            alert_bus, config.TRACKED_FIELDS, config.MIN_O_COUNT, config.MAX_O_COUNT,
        ),
        StreakBurstPattern(
            alert_bus, config.TRACKED_FIELDS, config.SEQ_COUNT_THRESHOLD,
        ),
        PairChainPattern(
            alert_bus, config.TRACKED_FIELDS, config.ANY_PAIR_MIN_GAP,
        ),
    ]
    return PatternEngine(history, patterns)


def main() -> None:
    db = RoundsDatabase(config.DB_PATH)

    preloaded_rounds = db.load_recent_rounds(config.HISTORY_PRELOAD_LIMIT)
    history = RoundHistory(config.HISTORY_MAXLEN, initial_rounds=preloaded_rounds)
    print(f"[Startup] История предзагружена: {history.total_rounds} раундов")

    sender = build_default_sender()
    alert_bus = AlertBus(config.PATTERN_ROUTING, sender, config.TELEGRAM_MAX_LEN)

    engine = build_engine(alert_bus, history)
    print(f"[Startup] Активных паттернов: {len(engine.patterns)}")
    for p in engine.patterns:
        print(f"  - {p.key}: {p.description}")

    command_notifier = build_notifier("main")
    handle_command = build_command_handler(db, command_notifier)

    cmd_thread = threading.Thread(
        target=run_forever_safe,
        args=(config.BOT_TOKENS["main"], config.TELEGRAM_CHAT_IDS, handle_command),
        daemon=True,
    )
    cmd_thread.start()

    try:
        listen_stream(db, engine)
    finally:
        db.close()


if __name__ == "__main__":
    main()