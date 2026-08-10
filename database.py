import os
import sqlite3
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "forcerank.db")


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def now():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    conn = get_db()
    cur = conn.cursor()

    # Semua user yang pernah terlihat bot
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            username TEXT,
            updated_at TEXT
        )
    """)

    # Lisensi pelanggan
    cur.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            expires_at TEXT,
            created_at TEXT
        )
    """)

    # Konfigurasi setiap grup
    cur.execute("""
        CREATE TABLE IF NOT EXISTS group_settings (
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            rank_link TEXT,
            rank_channel TEXT,
            rank_post_id INTEGER,
            updated_at TEXT
        )
    """)

    # Force rank
    cur.execute("""
        CREATE TABLE IF NOT EXISTS force_rank (
            chat_id INTEGER,
            user_id INTEGER,
            name TEXT,
            username TEXT,
            forced_by INTEGER,
            created_at TEXT,
            PRIMARY KEY(chat_id, user_id)
        )
    """)

    conn.commit()
    conn.close()


# ============================================================
# USER
# ============================================================

def save_user(user_id, name, username):
    conn = get_db()

    conn.execute("""
        INSERT INTO users
        (user_id, name, username, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id)
        DO UPDATE SET
            name=excluded.name,
            username=excluded.username,
            updated_at=excluded.updated_at
    """, (
        user_id,
        name,
        username,
        now()
    ))

    conn.commit()
    conn.close()


def find_user_by_username(username):
    username = username.replace("@", "").lower().strip()

    conn = get_db()

    row = conn.execute("""
        SELECT *
        FROM users
        WHERE LOWER(username)=?
        LIMIT 1
    """, (username,)).fetchone()

    conn.close()

    return row


def get_user(user_id):
    conn = get_db()

    row = conn.execute("""
        SELECT *
        FROM users
        WHERE user_id=?
    """, (user_id,)).fetchone()

    conn.close()

    return row


# ============================================================
# LICENSE
# ============================================================

def set_license(user_id, username, expires_at):
    conn = get_db()

    conn.execute("""
        INSERT INTO licenses
        (user_id, username, expires_at, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id)
        DO UPDATE SET
            username=excluded.username,
            expires_at=excluded.expires_at
    """, (
        user_id,
        username,
        expires_at,
        now()
    ))

    conn.commit()
    conn.close()


def get_license(user_id):
    conn = get_db()

    row = conn.execute("""
        SELECT *
        FROM licenses
        WHERE user_id=?
    """, (user_id,)).fetchone()

    conn.close()

    return row


def remove_license(user_id):
    conn = get_db()

    cur = conn.execute("""
        DELETE FROM licenses
        WHERE user_id=?
    """, (user_id,))

    deleted = cur.rowcount

    conn.commit()
    conn.close()

    return deleted > 0


def get_all_licenses():
    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM licenses
        ORDER BY expires_at DESC
    """).fetchall()

    conn.close()

    return rows


# ============================================================
# GROUP SETTINGS
# ============================================================

def save_group(
    chat_id,
    title
):
    conn = get_db()

    conn.execute("""
        INSERT INTO group_settings
        (chat_id, title, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(chat_id)
        DO UPDATE SET
            title=excluded.title,
            updated_at=excluded.updated_at
    """, (
        chat_id,
        title,
        now()
    ))

    conn.commit()
    conn.close()


def get_group(chat_id):
    conn = get_db()

    row = conn.execute("""
        SELECT *
        FROM group_settings
        WHERE chat_id=?
    """, (chat_id,)).fetchone()

    conn.close()

    return row


def set_rank_config(
    chat_id,
    rank_link,
    rank_channel,
    rank_post_id
):
    conn = get_db()

    conn.execute("""
        INSERT INTO group_settings
        (
            chat_id,
            rank_link,
            rank_channel,
            rank_post_id,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?)

        ON CONFLICT(chat_id)
        DO UPDATE SET
            rank_link=excluded.rank_link,
            rank_channel=excluded.rank_channel,
            rank_post_id=excluded.rank_post_id,
            updated_at=excluded.updated_at
    """, (
        chat_id,
        rank_link,
        rank_channel,
        rank_post_id,
        now()
    ))

    conn.commit()
    conn.close()


# ============================================================
# FORCE RANK
# ============================================================

def add_force_rank(
    chat_id,
    user_id,
    name,
    username,
    forced_by
):
    conn = get_db()

    conn.execute("""
        INSERT OR REPLACE INTO force_rank
        (
            chat_id,
            user_id,
            name,
            username,
            forced_by,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        chat_id,
        user_id,
        name,
        username,
        forced_by,
        now()
    ))

    conn.commit()
    conn.close()


def get_force_rank(chat_id, user_id):
    conn = get_db()

    row = conn.execute("""
        SELECT *
        FROM force_rank
        WHERE chat_id=?
        AND user_id=?
    """, (
        chat_id,
        user_id
    )).fetchone()

    conn.close()

    return row


def get_force_by_user(user_id):
    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM force_rank
        WHERE user_id=?
    """, (user_id,)).fetchall()

    conn.close()

    return rows


def get_force_list(chat_id):
    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM force_rank
        WHERE chat_id=?
        ORDER BY created_at ASC
    """, (chat_id,)).fetchall()

    conn.close()

    return rows


def remove_force_rank(chat_id, user_id):
    conn = get_db()

    cur = conn.execute("""
        DELETE FROM force_rank
        WHERE chat_id=?
        AND user_id=?
    """, (
        chat_id,
        user_id
    ))

    deleted = cur.rowcount

    conn.commit()
    conn.close()

    return deleted > 0