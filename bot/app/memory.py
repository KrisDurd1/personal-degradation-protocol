"""Память бота. SQLite локально, Postgres на сервере — код один и тот же.

Переключение по DATABASE_URL: Railway подставляет её сам, когда в проект
добавлен Postgres. Пусто — работаем на файле, как раньше.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .config import settings

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS users (
    user_id    INTEGER PRIMARY KEY,
    chat_id    INTEGER,
    username   TEXT,
    first_name TEXT,
    last_name  TEXT,
    language   TEXT,
    is_premium INTEGER,
    last_seen  TEXT,
    persona    TEXT    NOT NULL DEFAULT 'kolodets',
    dossier    TEXT,
    turns      INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    chat_id    INTEGER,
    tg_msg_id  INTEGER,
    role       TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    raw        TEXT,
    persona    TEXT,
    model      TEXT,
    latency_ms INTEGER,
    ts         TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(user_id, id DESC);
CREATE TABLE IF NOT EXISTS events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    chat_id INTEGER,
    kind    TEXT    NOT NULL,
    payload TEXT,
    ts      TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id, id DESC);
"""

SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS users (
    user_id    BIGINT PRIMARY KEY,
    chat_id    BIGINT,
    username   TEXT,
    first_name TEXT,
    last_name  TEXT,
    language   TEXT,
    is_premium INTEGER,
    last_seen  TEXT,
    persona    TEXT   NOT NULL DEFAULT 'kolodets',
    dossier    TEXT,
    turns      INTEGER NOT NULL DEFAULT 0,
    created_at TEXT   NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL,
    chat_id    BIGINT,
    tg_msg_id  BIGINT,
    role       TEXT   NOT NULL,
    content    TEXT   NOT NULL,
    raw        TEXT,
    persona    TEXT,
    model      TEXT,
    latency_ms INTEGER,
    ts         TEXT   NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(user_id, id DESC);
CREATE TABLE IF NOT EXISTS events (
    id      BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    chat_id BIGINT,
    kind    TEXT   NOT NULL,
    payload TEXT,
    ts      TEXT   NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id, id DESC);
"""


MIGRATIONS: dict[str, dict[str, str]] = {
    "users": {
        "chat_id": "BIGINT", "first_name": "TEXT", "last_name": "TEXT",
        "language": "TEXT", "is_premium": "INTEGER", "last_seen": "TEXT",
    },
    "messages": {"chat_id": "BIGINT", "tg_msg_id": "BIGINT"},
    "events": {"chat_id": "BIGINT", "username": "TEXT", "message_id": "BIGINT"},
}


def _to_pg(sql: str) -> str:
    """Переводит ? в $1, $2… — asyncpg понимает только такой синтаксис."""
    out, n = [], 0
    for ch in sql:
        if ch == "?":
            n += 1
            out.append(f"${n}")
        else:
            out.append(ch)
    return "".join(out)


class Memory:
    """Единый интерфейс поверх двух баз."""

    def __init__(self) -> None:
        self._sqlite: Any = None
        self._pool: Any = None

    @property
    def is_postgres(self) -> bool:
        return bool(settings.database_url)

    @property
    def backend(self) -> str:
        return "postgres" if self.is_postgres else f"sqlite ({settings.db_path})"

    async def open(self) -> None:
        if self.is_postgres:
            import asyncpg

            dsn = settings.database_url.replace("postgres://", "postgresql://", 1)
            self._pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
            async with self._pool.acquire() as conn:
                await conn.execute(SCHEMA_PG)
            await self._migrate()
            await self._views()
            log.info("Память: Postgres")
        else:
            import aiosqlite

            settings.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._sqlite = await aiosqlite.connect(settings.db_path)
            self._sqlite.row_factory = aiosqlite.Row
            await self._sqlite.executescript(SCHEMA_SQLITE)
            await self._sqlite.commit()
            await self._migrate()
            await self._views()
            log.info("Память: SQLite %s", settings.db_path)

    async def _columns(self, table: str) -> set[str]:
        if self.is_postgres:
            rows = await self._rows(
                "SELECT column_name AS name FROM information_schema.columns WHERE table_name=?",
                table,
            )
        else:
            rows = await self._rows(f"PRAGMA table_info({table})")
        return {r["name"] for r in rows}

    async def _migrate(self) -> None:
        """Дописывает колонки в базы, созданные прошлой версией."""
        for table, cols in MIGRATIONS.items():
            have = await self._columns(table)
            for col, kind in cols.items():
                if col not in have:
                    await self._exec(f"ALTER TABLE {table} ADD COLUMN {col} {kind}")
                    log.info("Миграция: %s.%s добавлена", table, col)

    async def _views(self) -> None:
        """Готовые витрины: открыл таблицу и всё видно, без SQL."""
        await self._exec("DROP VIEW IF EXISTS v_dialog")
        await self._exec(
            "CREATE VIEW v_dialog AS SELECT m.ts, u.username, u.first_name, "
            "m.user_id, m.chat_id, m.role, m.content, m.persona, m.model, "
            "m.latency_ms, m.raw FROM messages m LEFT JOIN users u "
            "ON u.user_id = m.user_id ORDER BY m.id DESC"
        )
        await self._exec("DROP VIEW IF EXISTS v_activity")
        await self._exec(
            "CREATE VIEW v_activity AS SELECT e.ts, e.username, e.user_id, "
            "e.chat_id, e.kind, e.payload, e.message_id FROM events e ORDER BY e.id DESC"
        )

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
        if self._sqlite:
            await self._sqlite.close()

    # --- низкий уровень ------------------------------------------------
    async def _exec(self, sql: str, *args: Any) -> None:
        if self.is_postgres:
            async with self._pool.acquire() as conn:
                await conn.execute(_to_pg(sql), *args)
        else:
            await self._sqlite.execute(sql, args)
            await self._sqlite.commit()

    async def _rows(self, sql: str, *args: Any) -> list[Any]:
        if self.is_postgres:
            async with self._pool.acquire() as conn:
                return list(await conn.fetch(_to_pg(sql), *args))
        async with self._sqlite.execute(sql, args) as cur:
            return list(await cur.fetchall())

    async def _row(self, sql: str, *args: Any) -> Any:
        rows = await self._rows(sql, *args)
        return rows[0] if rows else None

    # --- пользователи ---------------------------------------------------
    async def ensure_user(self, user: Any = None, chat_id: int | None = None) -> Any:
        """Заводит или обновляет карточку человека. user — объект из телеграма."""
        user_id = user.id
        insert = (
            "INSERT INTO users(user_id, persona, created_at) VALUES (?,?,?) "
            + ("ON CONFLICT (user_id) DO NOTHING" if self.is_postgres else "")
        )
        if not self.is_postgres:
            insert = insert.replace("INSERT INTO", "INSERT OR IGNORE INTO", 1)
        await self._exec(insert, user_id, settings.persona, _now())
        await self._exec(
            "UPDATE users SET chat_id=?, username=?, first_name=?, last_name=?, "
            "language=?, is_premium=?, last_seen=? WHERE user_id=?",
            chat_id,
            user.username,
            user.first_name,
            user.last_name,
            getattr(user, "language_code", None),
            1 if getattr(user, "is_premium", None) else 0,
            _now(),
            user_id,
        )
        return await self._row("SELECT * FROM users WHERE user_id=?", user_id)

    async def set_persona(self, user_id: int, persona_id: str) -> None:
        await self._exec("UPDATE users SET persona=? WHERE user_id=?", persona_id, user_id)

    async def set_dossier(self, user_id: int, dossier: str) -> None:
        await self._exec("UPDATE users SET dossier=? WHERE user_id=?", dossier, user_id)

    # --- переписка -------------------------------------------------------
    async def add(
        self,
        user_id: int,
        role: str,
        content: str,
        *,
        raw: str | None = None,
        chat_id: int | None = None,
        tg_msg_id: int | None = None,
        persona: str | None = None,
        model: str | None = None,
        latency_ms: int | None = None,
    ) -> int:
        await self._exec(
            "INSERT INTO messages(user_id, chat_id, tg_msg_id, role, content, raw, "
            "persona, model, latency_ms, ts) VALUES (?,?,?,?,?,?,?,?,?,?)",
            user_id, chat_id, tg_msg_id, role, content, raw, persona, model, latency_ms, _now(),
        )
        if role == "user":
            await self._exec("UPDATE users SET turns = turns + 1 WHERE user_id=?", user_id)
        row = await self._row("SELECT turns FROM users WHERE user_id=?", user_id)
        return int(row["turns"]) if row else 0

    async def history(self, user_id: int, limit: int | None = None) -> list[dict[str, str]]:
        n = limit or settings.history_turns
        rows = await self._rows(
            "SELECT role, content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT ?",
            user_id, n,
        )
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    # --- журнал ----------------------------------------------------------
    async def log(
        self,
        user_id: int,
        kind: str,
        payload: str | None = None,
        *,
        chat_id: int | None = None,
        username: str | None = None,
        message_id: int | None = None,
    ) -> None:
        await self._exec(
            "INSERT INTO events(user_id, chat_id, username, message_id, kind, payload, ts) "
            "VALUES (?,?,?,?,?,?,?)",
            user_id, chat_id, username, message_id, kind, payload, _now(),
        )

    async def ledger(self, user_id: int, limit: int = 30) -> list[Any]:
        return await self._rows(
            "SELECT kind, payload, ts FROM events WHERE user_id=? "
            "AND kind IN ('pulse','fork','seal','audit') ORDER BY id DESC LIMIT ?",
            user_id, limit,
        )

    async def wipe(self, user_id: int) -> None:
        for table in ("messages", "events", "users"):
            await self._exec(f"DELETE FROM {table} WHERE user_id=?", user_id)


memory = Memory()
