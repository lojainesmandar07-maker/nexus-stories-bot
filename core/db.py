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
        
        await db.commit()

