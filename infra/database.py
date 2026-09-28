"""
Работа с sqlite-базой раундов и экспорт в Excel.

Формат raund_data, который отдаёт наружу этот модуль:
{
    "round_public_id": str,
    "dice1": int,
    "dice2": int,
    "result_raw": str,
    "finished_at": str | None,
}
"""

import sqlite3
import threading

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment


class RoundsDatabase:
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS rounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round_id TEXT UNIQUE,
                round_public_id TEXT,
                dice1 INTEGER,
                dice2 INTEGER,
                result_raw TEXT,
                finished_at TEXT,
                saved_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._conn.commit()

    def save_round(self, payload: dict) -> dict | None:
        """Сохраняет раунд, если он ещё не был сохранён ранее (защита от дублей при реконнекте)."""
        result = payload.get("result")
        if not result:
            return None

        try:
            d1_str, d2_str = result.split("_")
            d1, d2 = int(d1_str), int(d2_str)
            if not (1 <= d1 <= 6 and 1 <= d2 <= 6):
                print("Некорректные значения кубиков:", result)
                return None
        except ValueError:
            print("Не удалось распарсить результат:", result)
            return None

        finished_at = payload.get("finishedAt")

        with self._lock:
            try:
                cur = self._conn.execute("""
                    INSERT OR IGNORE INTO rounds
                    (round_id, round_public_id, dice1, dice2, result_raw, finished_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    payload.get("roundId"),
                    payload.get("roundPublicId"),
                    d1, d2,
                    result,
                    finished_at,
                ))
                self._conn.commit()
            except Exception as e:
                print("Ошибка сохранения:", e)
                return None

            if cur.rowcount == 0:
                return None  # раунд уже был обработан ранее

        return {
            "round_public_id": payload.get("roundPublicId"),
            "dice1": d1,
            "dice2": d2,
            "result_raw": result,
            "finished_at": finished_at,
        }

    def load_recent_rounds(self, limit: int) -> list[dict]:
        """
        Загружает последние `limit` раундов в хронологическом порядке (старые -> новые).
        Используется для предзаполнения RoundHistory при старте бота.
        """
        with self._lock:
            cur = self._conn.execute("""
                SELECT round_public_id, dice1, dice2, result_raw, finished_at
                FROM rounds
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))
            rows = cur.fetchall()

        rows.reverse()

        return [
            {
                "round_public_id": r[0],
                "dice1": r[1],
                "dice2": r[2],
                "result_raw": r[3],
                "finished_at": r[4],
            }
            for r in rows
        ]

    def count(self) -> int:
        with self._lock:
            cur = self._conn.execute("SELECT COUNT(*) FROM rounds")
            return cur.fetchone()[0]

    def export_to_excel(self, limit: int, filename: str) -> int:
        with self._lock:
            cur = self._conn.execute("""
                SELECT round_public_id, dice1, dice2, result_raw, finished_at, saved_at
                FROM rounds
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))
            rows = cur.fetchall()

        rows.reverse()

        wb = Workbook()
        ws = wb.active
        ws.title = "Rounds"

        headers = ["Round ID", "Dice 1", "Dice 2", "Result Raw", "Finished At", "Saved At"]
        ws.append(headers)

        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center")

        for row in rows:
            ws.append(row)

        for col_cells in ws.columns:
            max_len = max(len(str(c.value)) if c.value is not None else 0 for c in col_cells)
            col_letter = col_cells[0].column_letter
            ws.column_dimensions[col_letter].width = max_len + 2

        try:
            wb.save(filename)
            print(f"[Excel] Экспортировано {len(rows)} раундов в {filename}")
            return len(rows)
        except Exception as e:
            print(f"[Ошибка экспорта в Excel]: {e}")
            return 0

    def close(self) -> None:
        self._conn.close()