"""
Локальное хранилище состояния квеста (SQLite, через aiosqlite).

Почему не хранить состояние прямо в Google-таблице:
Sheets API имеет заметную задержку и лимиты на количество запросов в минуту.
Если каждый шаг диалога (а их на человека 7-8) будет читать/писать строку в
таблице, бот будет "тормозить" и может упереться в лимиты при нескольких
участниках одновременно, а любая сетевая заминка сломает логику "не пропускай
этап". Поэтому источник истины для машины состояний — локальная SQLite-база
(быстро, атомарно, работает даже если Google API недоступен пару секунд), а
Google-таблица — это "витрина"/отчёт, в который бот зеркалит данные при каждом
изменении (см. sheets.py). Открыть/прочитать эту таблицу можно по ссылке в
любой момент, она всегда отражает актуальное состояние с небольшой задержкой.
"""
import asyncio
import json
from datetime import datetime, timezone

import aiosqlite

DB_PATH = "quest.db"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    vk_id INTEGER PRIMARY KEY,
    name TEXT,
    phone TEXT,
    step TEXT NOT NULL DEFAULT 'new',
    ticket_id TEXT,
    started_at TEXT,
    name_at TEXT,
    phone_at TEXT,
    sub_confirmed_at TEXT,
    qr2_at TEXT,
    qr3_at TEXT,
    finished_at TEXT,
    checkpoints_passed TEXT DEFAULT '',
    answer_attempts TEXT DEFAULT '[]'
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def connect(self):
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute(CREATE_TABLE_SQL)
        await self._conn.commit()

    async def close(self):
        if self._conn:
            await self._conn.close()

    async def get_user(self, vk_id: int) -> dict | None:
        async with self._lock:
            cur = await self._conn.execute("SELECT * FROM users WHERE vk_id = ?", (vk_id,))
            row = await cur.fetchone()
            return dict(row) if row else None

    async def create_user(self, vk_id: int) -> dict:
        async with self._lock:
            await self._conn.execute(
                "INSERT OR IGNORE INTO users (vk_id, step, started_at, checkpoints_passed) "
                "VALUES (?, 'new', ?, 'start')",
                (vk_id, now_iso()),
            )
            await self._conn.commit()
            cur = await self._conn.execute("SELECT * FROM users WHERE vk_id = ?", (vk_id,))
            row = await cur.fetchone()
            return dict(row)

    async def update_user(self, vk_id: int, **fields) -> dict | None:
        if not fields:
            return await self.get_user(vk_id)
        async with self._lock:
            cols = ", ".join(f"{k} = ?" for k in fields)
            values = list(fields.values()) + [vk_id]
            await self._conn.execute(f"UPDATE users SET {cols} WHERE vk_id = ?", values)
            await self._conn.commit()
            cur = await self._conn.execute("SELECT * FROM users WHERE vk_id = ?", (vk_id,))
            row = await cur.fetchone()
            return dict(row) if row else None

    async def add_checkpoint(self, vk_id: int, checkpoint: str):
        user = await self.get_user(vk_id)
        if user is None:
            return
        passed = user["checkpoints_passed"].split(",") if user["checkpoints_passed"] else []
        if checkpoint not in passed:
            passed.append(checkpoint)
        await self.update_user(vk_id, checkpoints_passed=",".join(passed))

    async def add_answer_attempt(self, vk_id: int, text: str, correct: bool):
        user = await self.get_user(vk_id)
        if user is None:
            return
        attempts = json.loads(user["answer_attempts"] or "[]")
        attempts.append({"text": text, "time": now_iso(), "correct": correct})
        await self.update_user(vk_id, answer_attempts=json.dumps(attempts, ensure_ascii=False))
