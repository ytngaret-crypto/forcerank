import os, sqlite3
from datetime import datetime, timezone

BASE_DIR=os.path.dirname(os.path.abspath(__file__))
DB_PATH=os.path.join(BASE_DIR,"forcerank.db")

def conn():
    c=sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory=sqlite3.Row
    return c

def init_db():
    c=conn(); cur=c.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS config(
      key TEXT PRIMARY KEY, value TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS force_users(
      chat_id INTEGER, user_id INTEGER, username TEXT, name TEXT,
      rank_filled INTEGER DEFAULT 0, subscribed INTEGER DEFAULT 0,
      created_at TEXT, PRIMARY KEY(chat_id,user_id))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS access(
      user_id INTEGER PRIMARY KEY, username TEXT, expires_at TEXT)""")
    c.commit(); c.close()

def set_config(k,v):
    c=conn(); c.execute("INSERT INTO config(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(k,str(v))); c.commit(); c.close()
def get_config(k,default=None):
    c=conn(); r=c.execute("SELECT value FROM config WHERE key=?",(k,)).fetchone(); c.close()
    return r["value"] if r else default

def add_force(chat_id,user_id,username,name):
    c=conn(); c.execute("""INSERT INTO force_users(chat_id,user_id,username,name,created_at)
      VALUES(?,?,?,?,?) ON CONFLICT(chat_id,user_id) DO UPDATE SET username=excluded.username,name=excluded.name""",
      (chat_id,user_id,username,name,datetime.now(timezone.utc).isoformat())); c.commit(); c.close()
def remove_force(chat_id,user_id):
    c=conn(); c.execute("DELETE FROM force_users WHERE chat_id=? AND user_id=?",(chat_id,user_id)); c.commit(); c.close()
def get_force(chat_id,user_id):
    c=conn(); r=c.execute("SELECT * FROM force_users WHERE chat_id=? AND user_id=?",(chat_id,user_id)).fetchone(); c.close(); return dict(r) if r else None
def list_force(chat_id):
    c=conn(); r=c.execute("SELECT * FROM force_users WHERE chat_id=? ORDER BY created_at",(chat_id,)); c.close(); return [dict(x) for x in r]

def mark_rank(chat_id,user_id):
    c=conn(); c.execute("UPDATE force_users SET rank_filled=1 WHERE chat_id=? AND user_id=?",(chat_id,user_id)); c.commit(); c.close()
def mark_sub(chat_id,user_id,val=1):
    c=conn(); c.execute("UPDATE force_users SET subscribed=? WHERE chat_id=? AND user_id=?",(val,chat_id,user_id)); c.commit(); c.close()

def set_access(user_id,username,expires_at):
    c=conn(); c.execute("INSERT INTO access(user_id,username,expires_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,expires_at=excluded.expires_at",(user_id,username,expires_at)); c.commit(); c.close()
def get_access(user_id):
    c=conn(); r=c.execute("SELECT * FROM access WHERE user_id=?",(user_id,)).fetchone(); c.close(); return dict(r) if r else None

def all_force():
    c=conn(); r=c.execute("SELECT * FROM force_users").fetchall(); c.close(); return [dict(x) for x in r]
