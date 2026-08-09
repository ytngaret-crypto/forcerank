import os
import sqlite3
from datetime import datetime


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "forcerank.db")


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
        CREATE TABLE IF NOT EXISTS force_rank (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            nama TEXT,
            username TEXT,
            forced_by INTEGER,
            forced_at TEXT,
            PRIMARY KEY (chat_id, user_id)
        )
    """)

    conn.commit()
    conn.close()


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
        INSERT OR REPLACE INTO force_rank
        (
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
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()


async def rank_comment_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    # ========================================================
    # CEK KOMENTAR POST RANK #9
    # ========================================================

    if not is_rank_comment(message):
        return

    user = message.from_user

    if not user:
        return

    logger.info(
        "Komentar rank terdeteksi: %s (%s)",
        user.full_name,
        user.id
    )

    # ========================================================
    # CARI FORCE RANK USER
    # ========================================================

    from database import get_force_rank_by_user

    records = get_force_rank_by_user(
        user.id
    )

    if not records:

        logger.info(
            "User %s komentar tetapi tidak sedang Force Rank.",
            user.id
        )

        return

    # ========================================================
    # PROSES SEMUA FORCE RANK USER
    # ========================================================

    for record in records:

        main_chat_id = record["chat_id"]

        nama = record["nama"]

        username = record["username"]

        forced_by = record["forced_by"]

        # ----------------------------------------------------
        # UNMUTE
        # ----------------------------------------------------

        try:

            await unmute_user(
                context.bot,
                main_chat_id,
                user.id
            )

        except Exception as e:

            logger.exception(e)

            continue

        # ----------------------------------------------------
        # HAPUS DATABASE
        # ----------------------------------------------------

        remove_force_rank(
            main_chat_id,
            user.id
        )

        # ----------------------------------------------------
        # USERNAME
        # ----------------------------------------------------

        if username:

            username_text = (
                "@"
                + html.escape(username)
            )

        else:

            username_text = (
                "Tidak ada username"
            )

        user_mention = mention_user(user)

        # ====================================================
        # NOTIFIKASI DI GRUP UTAMA
        # ====================================================

        group_text = (
            "✅ <b>FORCE RANK SELESAI</b>\n\n"

            f"👤 User: {user_mention}\n"
            f"🔹 Username: {username_text}\n\n"

            "📝 Rank: <b>SUDAH DIISI</b>\n"
            "💬 Komentar rank: <b>TERDETEKSI</b>\n"
            "🔊 Status: <b>UNMUTED OTOMATIS</b>\n\n"

            "🎉 User telah menyelesaikan "
            "Force Rank."
        )

        try:

            await context.bot.send_message(
                chat_id=main_chat_id,
                text=group_text,
                parse_mode="HTML"
            )

        except Exception as e:

            logger.exception(e)

        # ====================================================
        # NOTIFIKASI ADMIN
        # ====================================================

        admin_text = (
            "🔔 <b>NOTIFIKASI FORCE RANK</b>\n\n"

            f"👤 User: {user_mention}\n"
            f"🔹 Username: {username_text}\n\n"

            "✅ Telah mengisi rank\n"
            "🔊 Telah di-unmute otomatis\n\n"

            "📌 Komentar terdeteksi pada:\n"
            f"https://t.me/{RANK_CHANNEL}/{RANK_POST_ID}"
        )

        try:

            await context.bot.send_message(
                chat_id=forced_by,
                text=admin_text,
                parse_mode="HTML"
            )

        except Exception as e:

            logger.info(
                "Tidak dapat DM admin %s: %s",
                forced_by,
                e
            )

        # ====================================================
        # REPLY DI KOMENTAR
        # ====================================================

        try:

            await message.reply_text(
                "✅ Rank kamu telah terdeteksi.\n\n"
                "🔊 Kamu sudah di-unmute dari grup.\n"
                "🎉 Selamat datang kembali!"
            )

        except Exception as e:

            logger.info(
                "Gagal reply komentar: %s",
                e
    )
