import aiosqlite
import os
import json
from datetime import datetime, timedelta
from config import DB_PATH, ADMIN_IDS


async def get_conn():
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)
    conn = await aiosqlite.connect(DB_PATH)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    return conn


async def init_db():
    conn = await get_conn()
    try:
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                is_authenticated INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                last_active TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS coins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                cmc_slug TEXT,
                active INTEGER DEFAULT 1,
                added_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_analytics_created ON analytics(created_at);
            CREATE INDEX IF NOT EXISTS idx_users_telegram ON users(telegram_id);
        """)
        for sym, name in [("OWB", "OWB"), ("RAINBOW", "Rainbow")]:
            await conn.execute(
                "INSERT OR IGNORE INTO coins (symbol, name) VALUES (?, ?)",
                (sym, name),
            )
        await conn.commit()
    finally:
        await conn.close()


async def get_or_create_user(telegram_id: int, username: str = None, first_name: str = None):
    conn = await get_conn()
    try:
        cur = await conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        user = await cur.fetchone()
        if not user:
            is_admin = 1 if telegram_id in ADMIN_IDS else 0
            await conn.execute(
                "INSERT INTO users (telegram_id, username, first_name, is_admin) VALUES (?, ?, ?, ?)",
                (telegram_id, username, first_name, is_admin),
            )
            await conn.commit()
            cur = await conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
            user = await cur.fetchone()
        else:
            await conn.execute(
                "UPDATE users SET last_active = datetime('now'), username = ?, first_name = ? WHERE telegram_id = ?",
                (username or user["username"], first_name or user["first_name"], telegram_id),
            )
            if telegram_id in ADMIN_IDS and not user["is_admin"]:
                await conn.execute("UPDATE users SET is_admin = 1 WHERE telegram_id = ?", (telegram_id,))
            await conn.commit()
        return dict(user)
    finally:
        await conn.close()


async def authenticate_user(telegram_id: int):
    conn = await get_conn()
    try:
        await conn.execute("UPDATE users SET is_authenticated = 1 WHERE telegram_id = ?", (telegram_id,))
        await conn.commit()
    finally:
        await conn.close()


async def is_authenticated(telegram_id: int) -> bool:
    conn = await get_conn()
    try:
        cur = await conn.execute(
            "SELECT is_authenticated FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cur.fetchone()
        return bool(row and row["is_authenticated"])
    finally:
        await conn.close()


async def is_admin(telegram_id: int) -> bool:
    conn = await get_conn()
    try:
        cur = await conn.execute(
            "SELECT is_admin, is_authenticated FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cur.fetchone()
        return bool(row and row["is_admin"] and row["is_authenticated"])
    finally:
        await conn.close()


async def get_active_coins():
    conn = await get_conn()
    try:
        cur = await conn.execute("SELECT * FROM coins WHERE active = 1")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def add_coin(symbol: str, name: str, cmc_slug: str = None):
    conn = await get_conn()
    try:
        await conn.execute(
            "INSERT OR REPLACE INTO coins (symbol, name, cmc_slug, active) VALUES (?, ?, ?, 1)",
            (symbol.upper(), name, cmc_slug),
        )
        await conn.commit()
    finally:
        await conn.close()


async def remove_coin(symbol: str):
    conn = await get_conn()
    try:
        await conn.execute("UPDATE coins SET active = 0 WHERE symbol = ?", (symbol.upper(),))
        await conn.commit()
    finally:
        await conn.close()


async def get_authenticated_users():
    conn = await get_conn()
    try:
        cur = await conn.execute("SELECT * FROM users WHERE is_authenticated = 1")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def log_action(telegram_id: int, action: str, details: str = None):
    conn = await get_conn()
    try:
        await conn.execute(
            "INSERT INTO analytics (telegram_id, action, details) VALUES (?, ?, ?)",
            (telegram_id, action, details),
        )
        await conn.commit()
    finally:
        await conn.close()


async def get_analytics():
    conn = await get_conn()
    try:
        total = (await (await conn.execute("SELECT COUNT(*) as c FROM users")).fetchone())["c"]
        authed = (
            await (
                await conn.execute("SELECT COUNT(*) as c FROM users WHERE is_authenticated = 1")
            ).fetchone()
        )["c"]

        now_str = datetime.utcnow().isoformat()
        day_ago = (datetime.utcnow() - timedelta(days=1)).isoformat()
        week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        month_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()

        active_day = (
            await (
                await conn.execute(
                    "SELECT COUNT(*) as c FROM users WHERE last_active >= ?", (day_ago,)
                )
            ).fetchone()
        )["c"]
        active_week = (
            await (
                await conn.execute(
                    "SELECT COUNT(*) as c FROM users WHERE last_active >= ?", (week_ago,)
                )
            ).fetchone()
        )["c"]
        active_month = (
            await (
                await conn.execute(
                    "SELECT COUNT(*) as c FROM users WHERE last_active >= ?", (month_ago,)
                )
            ).fetchone()
        )["c"]

        actions_today = (
            await (
                await conn.execute(
                    "SELECT COUNT(*) as c FROM analytics WHERE created_at >= ?", (day_ago,)
                )
            ).fetchone()
        )["c"]

        top_actions = await (
            await conn.execute(
                "SELECT action, COUNT(*) as c FROM analytics WHERE created_at >= ? GROUP BY action ORDER BY c DESC LIMIT 10",
                (week_ago,),
            )
        ).fetchall()

        return {
            "total_users": total,
            "authenticated_users": authed,
            "active_24h": active_day,
            "active_7d": active_week,
            "active_30d": active_month,
            "actions_today": actions_today,
            "top_actions_week": [(r["action"], r["c"]) for r in top_actions],
        }
    finally:
        await conn.close()


async def get_all_users_list():
    conn = await get_conn()
    try:
        cur = await conn.execute(
            "SELECT telegram_id, username, first_name, is_authenticated, is_admin, created_at, last_active FROM users ORDER BY created_at DESC"
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        await conn.close()
