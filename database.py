import aiosqlite
from datetime import datetime, timezone
from typing import Optional

DB_PATH = "wordle.db"


async def init_db(db_path: str = DB_PATH) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS wordle_results (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id    TEXT NOT NULL,
                channel_id    TEXT NOT NULL,
                guild_id      TEXT NOT NULL,
                user_id       TEXT NOT NULL,
                wordle_number INTEGER,
                score         INTEGER,
                timestamp     TEXT NOT NULL,
                UNIQUE(message_id, user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scan_state (
                channel_id      TEXT PRIMARY KEY,
                last_message_id TEXT,
                last_scan_time  TEXT
            )
        """)
        await db.commit()


async def upsert_result(db_path: str, row: dict) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO wordle_results
                (message_id, channel_id, guild_id, user_id, wordle_number, score, timestamp)
            VALUES (:message_id, :channel_id, :guild_id, :user_id, :wordle_number, :score, :timestamp)
            """,
            row,
        )
        await db.commit()


async def upsert_results_bulk(db_path: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.executemany(
            """
            INSERT OR IGNORE INTO wordle_results
                (message_id, channel_id, guild_id, user_id, wordle_number, score, timestamp)
            VALUES (:message_id, :channel_id, :guild_id, :user_id, :wordle_number, :score, :timestamp)
            """,
            rows,
        )
        await db.commit()
        return cursor.rowcount


async def get_results(
    db_path: str,
    user_id: str,
    channel_id: str,
    after_dt: Optional[datetime] = None,
) -> list[dict]:
    query = """
        SELECT wordle_number, score, timestamp
        FROM wordle_results
        WHERE user_id = ? AND channel_id = ?
    """
    params: list = [user_id, channel_id]
    if after_dt is not None:
        query += " AND timestamp >= ?"
        params.append(after_dt.isoformat())
    query += " ORDER BY timestamp ASC"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_scan_state(db_path: str, channel_id: str) -> Optional[str]:
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT last_message_id FROM scan_state WHERE channel_id = ?",
            (str(channel_id),),
        ) as cursor:
            row = await cursor.fetchone()
    return row[0] if row else None


async def update_scan_state(db_path: str, channel_id: str, last_message_id: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO scan_state (channel_id, last_message_id, last_scan_time)
            VALUES (?, ?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET
                last_message_id = excluded.last_message_id,
                last_scan_time  = excluded.last_scan_time
            """,
            (str(channel_id), str(last_message_id), datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()
