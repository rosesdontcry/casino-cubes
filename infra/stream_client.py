"""
Клиент SSE-стрима казино: подключается, парсит события,
сохраняет завершённые раунды в БД и передаёт их в PatternEngine.
"""

import json
import time
from datetime import datetime

import requests

import config
from infra.database import RoundsDatabase
from core.pattern_engine import PatternEngine


def listen_stream(db: RoundsDatabase, engine: PatternEngine) -> None:
    while True:
        try:
            print("Подключение к потоку событий...")
            print(f"Активных паттернов: {len(engine.patterns)}")
            print("─" * 37)

            resp = requests.get(
                config.STREAM_URL,
                params=config.STREAM_PARAMS,
                headers=config.STREAM_HEADERS,
                stream=True,
                timeout=(config.STREAM_CONNECT_TIMEOUT, config.STREAM_READ_TIMEOUT),
            )
            resp.raise_for_status()

            for raw_line in resp.iter_lines(decode_unicode=True):
                if raw_line is None:
                    continue
                line = raw_line.strip()

                if not line.startswith("data:"):
                    continue
                data_str = line[len("data:"):].strip()
                if not data_str:
                    continue

                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                event_kind = data.get("type")
                payload = data.get("payload", {})

                if event_kind == "round_started":
                    print(f"[{_now()}] ▶ Раунд {payload.get('roundPublicId')} начался")

                elif event_kind == "round_finished":
                    round_data = db.save_round(payload)

                    if round_data:
                        d1 = round_data["dice1"]
                        d2 = round_data["dice2"]
                        pid = round_data["round_public_id"]

                        print(f"[{_now()}] ✅ {pid}   🔴{d1} vs {d2}🔵")

                        engine.process_round(round_data)

        except requests.exceptions.RequestException as e:
            print(f"\nОбрыв соединения, реконнект через {config.STREAM_RECONNECT_DELAY} сек: {e}")
            time.sleep(config.STREAM_RECONNECT_DELAY)
        except KeyboardInterrupt:
            print("\nОстановлено.")
            break
        except Exception as e:
            print(f"\nНеожиданная ошибка: {e}. Реконнект через {config.STREAM_RECONNECT_DELAY} сек.")
            time.sleep(config.STREAM_RECONNECT_DELAY)


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")