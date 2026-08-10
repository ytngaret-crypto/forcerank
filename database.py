import os
import sqlite3
from datetime import datetime


# ============================================================
# DATABASE
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

DB_PATH = os.path.join(
    BASE_DIR,
    "forcerank.db"
)


# ============================================================
# CONNECTION
# ============================================================

def get_connection():

    conn = sqlite3.connect(
        DB_PATH,
        check_same_thread=False
    )

    conn.row_factory = sqlite3.Row

    return conn


# ============================================================
# INIT DATABASE
# ============================================================

def init_db():

    conn = get_connection()
    cursor = conn.cursor()

    # --------------------------------------------------------
    # FORCE RANK
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS force_rank (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            nama TEXT,
            username TEXT,
            forced_by INTEGER,
            forced_at TEXT,
            PRIMARY KEY (
                chat_id,
                user_id
            )
        )
    """)

    # --------------------------------------------------------
    # USERS
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            nama TEXT,
            username TEXT,
            last_seen TEXT,
            PRIMARY KEY (
                chat_id,
                user_id
            )
        )
    """)

    conn.commit()
    conn.close()


# ============================================================
# SAVE / UPDATE USER
# ============================================================

def save_user(
    chat_id,
    user_id,
    nama,
    username
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO users (
            chat_id,
            user_id,
            nama,
            username,
            last_seen
        )
        VALUES (?, ?, ?, ?, ?)

        ON CONFLICT (
            chat_id,
            user_id
        )

        DO UPDATE SET
            nama = excluded.nama,
            username = excluded.username,
            last_seen = excluded.last_seen
    """, (
        chat_id,
        user_id,
        nama,
        username,
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    ))

    conn.commit()
    conn.close()


# ============================================================
# FIND USER BY USERNAME
# ============================================================

def find_user_by_username(
    chat_id,
    username
):

    if not username:
        return None

    username = username.lstrip("@").lower()

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
# ADD FORCE RANK
# ============================================================

def add_force_rank(
    chat_id,
    user_id,
    nama,
    username,
    forced_by
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO force_rank (
            chat_id,
            user_id,
            nama,
            username,
            forced_by,
            forced_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        chat_id,
        user_id,
        nama,
        username,
        forced_by,
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    ))

    conn.commit()
    conn.close()


# ============================================================
# GET FORCE RANK
# ============================================================

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


# ============================================================
# GET FORCE RANK BY USER
# ============================================================

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


# ============================================================
# REMOVE FORCE RANK
# ============================================================

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

    conn.commit()

    deleted = cursor.rowcount

    conn.close()

    return deleted > 0


# ============================================================
# GET ALL FORCE RANK
# ============================================================

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
