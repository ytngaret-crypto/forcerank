import os
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "forcerank.db")


def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER,
            user_id INTEGER,
            name TEXT,
            username TEXT,
            updated_at TEXT,
            PRIMARY KEY (chat_id, user_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS force_rank (
            chat_id INTEGER,
            user_id INTEGER,
            name TEXT,
            username TEXT,
            forced_by INTEGER,
            created_at TEXT,
            PRIMARY KEY (chat_id, user_id)
        )
    """)

    conn.commit()
    conn.close()


def save_user(chat_id, user_id, name, username):
    conn = db()
    conn.execute("""
        INSERT INTO users
        (chat_id, user_id, name, username, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(chat_id, user_id)
        DO UPDATE SET
            name=excluded.name,
            username=excluded.username,
            updated_at=excluded.updated_at
    """, (
        chat_id,
        user_id,
        name,
        username,
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()


def find_user(chat_id, username):
    username = username.replace("@", "").lower()

    conn = db()
    row = conn.execute("""
        SELECT *
        FROM users
        WHERE chat_id=?
        AND LOWER(username)=?
        LIMIT 1
    """, (
        chat_id,
        username
    )).fetchone()

    conn.close()
    return row


def add_force_rank(
    chat_id,
    user_id,
    name,
    username,
    forced_by
):
    conn = db()

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
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()


def get_force_rank(chat_id, user_id):
    conn = db()

    row = conn.execute("""
        SELECT *
        FROM force_rank
        WHERE chat_id=?
        AND user_id=?
        LIMIT 1
    """, (
        chat_id,
        user_id
    )).fetchone()

    conn.close()
    return row


def get_all_force_rank(chat_id):
    conn = db()

    rows = conn.execute("""
        SELECT *
        FROM force_rank
        WHERE chat_id=?
        ORDER BY created_at ASC
    """, (
        chat_id,
    )).fetchall()

    conn.close()
    return rows


def get_force_rank_by_user(user_id):
    conn = db()

    rows = conn.execute("""
        SELECT *
        FROM force_rank
        WHERE user_id=?
    """, (
        user_id,
    )).fetchall()

    conn.close()
    return rows


def remove_force_rank(chat_id, user_id):
    conn = db()

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
