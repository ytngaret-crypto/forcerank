import os
import sqlite3
from datetime import datetime


BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

DB_PATH = os.path.join(
    BASE_DIR,
    "forcerank.db"
)


def get_connection():
    conn = sqlite3.connect(
        DB_PATH,
        check_same_thread=False
    )

    conn.row_factory = sqlite3.Row

    return conn


def init_db():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            name TEXT,
            username TEXT,
            last_seen TEXT,
            PRIMARY KEY(chat_id, user_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS force_rank (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            name TEXT,
            username TEXT,
            forced_by INTEGER,
            forced_at TEXT,
            PRIMARY KEY(chat_id, user_id)
        )
    """)

    conn.commit()
    conn.close()


# ============================================================
# USER
# ============================================================

def save_user(
    chat_id,
    user_id,
    name,
    username
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO users (
            chat_id,
            user_id,
            name,
            username,
            last_seen
        )
        VALUES (?, ?, ?, ?, ?)

        ON CONFLICT(chat_id, user_id)
        DO UPDATE SET
            name = excluded.name,
            username = excluded.username,
            last_seen = excluded.last_seen
    """, (
        chat_id,
        user_id,
        name,
        username,
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    ))

    conn.commit()
    conn.close()


def find_user_by_username(
    chat_id,
    username
):

    username = (
        username
        .replace("@", "")
        .strip()
        .lower()
    )

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM users
        WHERE chat_id = ?
        AND LOWER(username) = ?
        LIMIT 1
    """, (
        chat_id,
        username
    ))

    result = cursor.fetchone()

    conn.close()

    return result


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

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO force_rank (
            chat_id,
            user_id,
            name,
            username,
            forced_by,
            forced_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        chat_id,
        user_id,
        name,
        username,
        forced_by,
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    ))

    conn.commit()
    conn.close()


def get_force_rank(
    chat_id,
    user_id
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM force_rank
        WHERE chat_id = ?
        AND user_id = ?
        LIMIT 1
    """, (
        chat_id,
        user_id
    ))

    result = cursor.fetchone()

    conn.close()

    return result


def get_all_force_rank(
    chat_id
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM force_rank
        WHERE chat_id = ?
        ORDER BY forced_at ASC
    """, (
        chat_id,
    ))

    results = cursor.fetchall()

    conn.close()

    return results


def get_force_rank_by_user(
    user_id
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM force_rank
        WHERE user_id = ?
    """, (
        user_id,
    ))

    results = cursor.fetchall()

    conn.close()

    return results


def remove_force_rank(
    chat_id,
    user_id
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM force_rank
        WHERE chat_id = ?
        AND user_id = ?
    """, (
        chat_id,
        user_id
    ))

    deleted = cursor.rowcount

    conn.commit()
    conn.close()

    return deleted > 0
