# basedata.py
import os
import sqlite3
import threading
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "forcerank.db")

_lock = threading.RLock()


def _conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _lock:
        conn = _conn()
        cur = conn.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS access (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            name TEXT,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS groups (
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            rank_link TEXT,
            rank_channel TEXT,
            rank_post_id INTEGER,
            sub_channel TEXT,
            updated_by INTEGER,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS forced (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT,
            name TEXT,
            forced_at TEXT NOT NULL,
            rank_filled INTEGER DEFAULT 0,
            subscribed INTEGER DEFAULT 0,
            PRIMARY KEY(chat_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS seen_users (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT,
            name TEXT,
            last_seen TEXT NOT NULL,
            PRIMARY KEY(chat_id, user_id)
        );
        """)
        conn.commit()
        conn.close()


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def add_or_extend_access(user_id, username, name, duration_days):
    with _lock:
        conn = _conn()
        cur = conn.cursor()
        row = cur.execute(
            "SELECT expires_at FROM access WHERE user_id=?",
            (user_id,)
        ).fetchone()
        now = now_utc()
        if row:
            try:
                old = datetime.fromisoformat(row["expires_at"])
                if old.tzinfo is None:
                    old = old.replace(tzinfo=timezone.utc)
            except Exception:
                old = now
            start = old if old > now else now
            expires = start + timedelta(days=duration_days)
            cur.execute(
                """UPDATE access
                   SET username=?, name=?, expires_at=?
                   WHERE user_id=?""",
                (username, name, iso(expires), user_id)
            )
        else:
            expires = now + timedelta(days=duration_days)
            cur.execute(
                """INSERT INTO access
                   (user_id, username, name, expires_at, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, username, name, iso(expires), iso(now))
            )
        conn.commit()
        conn.close()
        return expires


def set_access_until(user_id, username, name, expires_at):
    with _lock:
        conn = _conn()
        conn.execute(
            """INSERT INTO access(user_id,username,name,expires_at,created_at)
               VALUES(?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
               username=excluded.username,
               name=excluded.name,
               expires_at=excluded.expires_at""",
            (user_id, username, name, iso(expires_at), iso(now_utc()))
        )
        conn.commit()
        conn.close()


def remove_access(user_id):
    with _lock:
        conn = _conn()
        conn.execute("DELETE FROM access WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()


def get_access(user_id):
    with _lock:
        conn = _conn()
        row = conn.execute(
            "SELECT * FROM access WHERE user_id=?", (user_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None


def has_active_access(user_id):
    row = get_access(user_id)
    if not row:
        return False
    try:
        exp = datetime.fromisoformat(row["expires_at"])
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp > now_utc()
    except Exception:
        return False


def list_access():
    with _lock:
        conn = _conn()
        rows = conn.execute(
            "SELECT * FROM access ORDER BY expires_at DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


def save_group(chat_id, title=None, updated_by=None, **fields):
    allowed = {
        "rank_link", "rank_channel", "rank_post_id", "sub_channel"
    }
    with _lock:
        conn = _conn()
        row = conn.execute(
            "SELECT * FROM groups WHERE chat_id=?", (chat_id,)
        ).fetchone()
        data = dict(row) if row else {
            "chat_id": chat_id,
            "title": title or "",
            "rank_link": None,
            "rank_channel": None,
            "rank_post_id": None,
            "sub_channel": None,
            "updated_by": None,
            "updated_at": None,
        }
        if title is not None:
            data["title"] = title
        for k, v in fields.items():
            if k in allowed:
                data[k] = v
        data["updated_by"] = updated_by
        data["updated_at"] = iso(now_utc())
        conn.execute(
            """INSERT INTO groups
               (chat_id,title,rank_link,rank_channel,rank_post_id,
                sub_channel,updated_by,updated_at)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(chat_id) DO UPDATE SET
               title=excluded.title,
               rank_link=excluded.rank_link,
               rank_channel=excluded.rank_channel,
               rank_post_id=excluded.rank_post_id,
               sub_channel=excluded.sub_channel,
               updated_by=excluded.updated_by,
               updated_at=excluded.updated_at""",
            (
                data["chat_id"], data["title"], data["rank_link"],
                data["rank_channel"], data["rank_post_id"],
                data["sub_channel"], data["updated_by"], data["updated_at"]
            )
        )
        conn.commit()
        conn.close()


def get_group(chat_id):
    with _lock:
        conn = _conn()
        row = conn.execute(
            "SELECT * FROM groups WHERE chat_id=?", (chat_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None


def save_seen_user(chat_id, user_id, username, name):
    with _lock:
        conn = _conn()
        conn.execute(
            """INSERT INTO seen_users(chat_id,user_id,username,name,last_seen)
               VALUES(?,?,?,?,?)
               ON CONFLICT(chat_id,user_id) DO UPDATE SET
               username=excluded.username,
               name=excluded.name,
               last_seen=excluded.last_seen""",
            (chat_id, user_id, username, name, iso(now_utc()))
        )
        conn.commit()
        conn.close()


def find_seen_user(chat_id, username):
    username = username.lstrip("@").lower()
    with _lock:
        conn = _conn()
        row = conn.execute(
            """SELECT * FROM seen_users
               WHERE chat_id=? AND lower(username)=?
               ORDER BY last_seen DESC LIMIT 1""",
            (chat_id, username)
        ).fetchone()
        conn.close()
        return dict(row) if row else None


def add_force(chat_id, user_id, username, name):
    with _lock:
        conn = _conn()
        conn.execute(
            """INSERT INTO forced
               (chat_id,user_id,username,name,forced_at,rank_filled,subscribed)
               VALUES(?,?,?,?,?,0,0)
               ON CONFLICT(chat_id,user_id) DO UPDATE SET
               username=excluded.username,
               name=excluded.name""",
            (chat_id, user_id, username, name, iso(now_utc()))
        )
        conn.commit()
        conn.close()


def remove_force(chat_id, user_id):
    with _lock:
        conn = _conn()
        conn.execute(
            "DELETE FROM forced WHERE chat_id=? AND user_id=?",
            (chat_id, user_id)
        )
        conn.commit()
        conn.close()


def get_force(chat_id, user_id):
    with _lock:
        conn = _conn()
        row = conn.execute(
            "SELECT * FROM forced WHERE chat_id=? AND user_id=?",
            (chat_id, user_id)
        ).fetchone()
        conn.close()
        return dict(row) if row else None


def list_forced(chat_id):
    with _lock:
        conn = _conn()
        rows = conn.execute(
            "SELECT * FROM forced WHERE chat_id=? ORDER BY forced_at DESC",
            (chat_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


def set_rank_filled(chat_id, user_id, value=True):
    with _lock:
        conn = _conn()
        conn.execute(
            "UPDATE forced SET rank_filled=? WHERE chat_id=? AND user_id=?",
            (1 if value else 0, chat_id, user_id)
        )
        conn.commit()
        conn.close()


def set_subscribed(chat_id, user_id, value=True):
    with _lock:
        conn = _conn()
        conn.execute(
            "UPDATE forced SET subscribed=? WHERE chat_id=? AND user_id=?",
            (1 if value else 0, chat_id, user_id)
        )
        conn.commit()
        conn.close()


def all_forced():
    with _lock:
        conn = _conn()
        rows = conn.execute("SELECT * FROM forced").fetchall()
        conn.close()
        return [dict(r) for r in rows]
