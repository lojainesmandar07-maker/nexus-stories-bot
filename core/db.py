from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Awaitable, Callable, TypeVar

import aiosqlite

DB_PATH = os.getenv("DB_PATH", "data/nexus.db")

T = TypeVar("T")


@asynccontextmanager
async def get_connection() -> AsyncIterator[aiosqlite.Connection]:
    db = await aiosqlite.connect(DB_PATH)
    try:
        yield db
    finally:
        await db.close()


async def table_exists(db: aiosqlite.Connection, table_name: str) -> bool:
    cursor = await db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    )
    return (await cursor.fetchone()) is not None


async def run_read(operation: Callable[[aiosqlite.Connection], Awaitable[T]]) -> T:
    async with get_connection() as db:
        return await operation(db)


async def run_write(operation: Callable[[aiosqlite.Connection], Awaitable[T]]) -> T:
    async with get_connection() as db:
        try:
            result = await operation(db)
            await db.commit()
            return result
        except Exception:
            await db.rollback()
            raise


async def init_db() -> None:
    """Consolidated database table schema initialization."""
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        # Enable foreign key support in SQLite
        await db.execute("PRAGMA foreign_keys = ON;")
        
        # 1. Story Plays
        await db.execute("""
            CREATE TABLE IF NOT EXISTS story_plays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                story_id INTEGER,
                ending_id TEXT,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 2. Shared Endings
        await db.execute("""
            CREATE TABLE IF NOT EXISTS shared_endings (
                id TEXT PRIMARY KEY,
                user_id INTEGER,
                story_id INTEGER,
                ending_id TEXT,
                ending_text TEXT,
                shared_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 3. Multiplayer Sessions
        await db.execute("""
            CREATE TABLE IF NOT EXISTS multiplayer_sessions (
                session_id TEXT PRIMARY KEY,
                story_id TEXT,
                status TEXT, -- 'lobby', 'active', 'finished'
                players TEXT, -- JSON mapping of discord_id -> role_id
                current_node_states TEXT, -- JSON mapping of role_id -> current_node_id
                flags TEXT, -- JSON mapping of flags set in session
                host_id TEXT,
                channel_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migration: Add host_id and channel_id to existing database if missing
        cursor = await db.execute("PRAGMA table_info(multiplayer_sessions);")
        columns = [row[1] for row in await cursor.fetchall()]
        if columns:
            if "host_id" not in columns:
                await db.execute("ALTER TABLE multiplayer_sessions ADD COLUMN host_id TEXT;")
            if "channel_id" not in columns:
                await db.execute("ALTER TABLE multiplayer_sessions ADD COLUMN channel_id INTEGER;")

        await db.commit()


# Helpers for multiplayer sessions
import json
from typing import Dict, Any, Optional

async def save_multiplayer_session(
    session_id: str,
    story_id: str,
    status: str,
    players: Dict[str, str],
    current_node_states: Dict[str, str],
    flags: list[str],
    host_id: str = "",
    channel_id: int = 0
) -> None:
    async with get_connection() as db:
        await db.execute("""
            INSERT INTO multiplayer_sessions (session_id, story_id, status, players, current_node_states, flags, host_id, channel_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                status=excluded.status,
                players=excluded.players,
                current_node_states=excluded.current_node_states,
                flags=excluded.flags,
                host_id=excluded.host_id,
                channel_id=excluded.channel_id
        """, (
            session_id,
            story_id,
            status,
            json.dumps(players),
            json.dumps(current_node_states),
            json.dumps(flags),
            host_id,
            channel_id
        ))
        await db.commit()

async def load_multiplayer_session(session_id: str) -> Optional[Dict[str, Any]]:
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT story_id, status, players, current_node_states, flags, host_id, channel_id FROM multiplayer_sessions WHERE session_id = ?",
            (session_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None

        return {
            "session_id": session_id,
            "story_id": row[0],
            "status": row[1],
            "players": json.loads(row[2]),
            "current_node_states": json.loads(row[3]),
            "flags": json.loads(row[4]),
            "host_id": row[5] if row[5] is not None else "",
            "channel_id": row[6] if row[6] is not None else 0
        }
