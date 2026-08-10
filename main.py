# main.py
# FORCE RANK BOT - Railway ready
# Python 3.10+ / python-telegram-bot 21.x
#
# ENV WAJIB:
# BOT_TOKEN=token_bot
# OWNER_ID=123456789
# OWNER_ID_2=987654321
#
# OWNER_ID_2 boleh dikosongkan jika hanya 1 owner.
#
# Semua data tersimpan di forcerank.db.

import os
import re
import logging
from datetime import datetime, timezone

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatPermissions,
)
from telegram.constants import ChatType
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import basedata as db


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

try:
    OWNER_ID = int(os.getenv("OWNER_ID", "0"))
except ValueError:
    OWNER_ID = 0

try:
    OWNER_ID_2 = int(os.getenv("OWNER_ID_2", "0"))
except ValueError:
    OWNER_ID_2 = 0

OWNER_IDS = {x for x in (OWNER_ID, OWNER_ID_2) if x}

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN belum diisi di Railway Variables.")

if not OWNER_IDS:
    raise RuntimeError("OWNER_ID belum diisi di Railway Variables.")


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("forcerank")


# ============================================================
# HELPERS
# ============================================================

def is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS


def mention(user) -> str:
    if user.username:
        return f"@{user.username}"
    return user.full_name


def parse_duration(value: str):
    """
    Contoh:
    30d = 30 hari
    12h = 12 jam
    30m = 30 menit
    """
    m = re.fullmatch(r"(\d+)\s*([dhm])", value.lower())
    if not m:
        return None

    amount = int(m.group(1))
    unit = m.group(2)

    if amount <= 0:
        return None

    if unit == "d":
        return amount, "hari"
    if unit == "h":
        return amount / 24, "jam"
    return amount / 1440, "menit"


def duration_to_days(value: str):
    m = re.fullmatch(r"(\d+)\s*([dhm])", value.lower())
    if not m:
        return None
    amount = int(m.group(1))
    unit = m.group(2)
    if unit == "d":
        return amount
    if unit == "h":
        return amount / 24
    return amount / 1440


def format_expiry(expires_at: str) -> str:
    try:
        dt = datetime.fromisoformat(expires_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime("%d-%m-%Y %H:%M UTC")
    except Exception:
        return expires_at


def parse_rank_link(link: str):
    """
    Mendukung:
    https://t.me/channel/123
    https://t.me/c/1234567890/123
    """
    link = link.strip()
    m = re.match(
        r"^https?://t\.me/([^/]+)/(\d+)(?:\?.*)?$",
        link,
        re.I,
    )
    if m:
        return m.group(1), int(m.group(2))

    m = re.match(
        r"^https?://t\.me/c/(\d+)/(\d+)(?:\?.*)?$",
        link,
        re.I,
    )
    if m:
        return f"-100{m.group(1)}", int(m.group(2))

    return None, None


def normalize_channel(value: str):
    value = value.strip()
    if value.startswith("https://t.me/"):
        value = value.replace("https://t.me/", "", 1)
        value = value.split("/")[0]
    return value


def group_config_ready(chat_id):
    cfg = db.get_group(chat_id)
    if not cfg:
        return False, "Link rank dan channel subscribe belum diatur."
    if not cfg.get("rank_link"):
        return False, "Link rank belum diatur."
    if not cfg.get("sub_channel"):
        return False, "Channel wajib subscribe belum diatur."
    return True, cfg


async def active_required(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_owner(user.id):
        return True

    if db.has_active_access(user.id):
        return True

    text = (
        "🔒 <b>AKSES BELUM AKTIF</b>\n\n"
        "Akun kamu belum memiliki akses Force Rank.\n\n"
        "Silakan beli akses terlebih dahulu."
    )

    if update.callback_query:
        await update.callback_query.answer(
            "🔒 Akses kamu belum aktif.",
            show_alert=True,
        )
        await update.callback_query.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "💰 BUY AKSES BOT",
                    callback_data="buy_access"
                )]
            ]),
            parse_mode="HTML",
        )
    else:
        await update.effective_message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "💰 BUY AKSES BOT",
                    callback_data="buy_access"
                )]
            ]),
            parse_mode="HTML",
        )
    return False


async def admin_required(update: Update, context, user_id=None):
    chat = update.effective_chat
    user = update.effective_user
    uid = user_id or user.id

    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await update.effective_message.reply_text(
            "❌ Perintah ini hanya bisa dipakai di grup."
        )
        return False

    try:
        member = await context.bot.get_chat_member(chat.id, uid)
        if member.status not in ("administrator", "creator"):
            await update.effective_message.reply_text(
                "❌ Hanya admin grup yang bisa menggunakan fitur ini."
            )
            return False
        return True
    except Exception as e:
        logger.exception("Gagal cek admin: %s", e)
        await update.effective_message.reply_text(
            "❌ Bot tidak bisa mengecek status admin.\n"
            "Pastikan bot menjadi admin grup."
        )
        return False


async def owner_required(update: Update):
    user = update.effective_user
    if not is_owner(user.id):
        await update.effective_message.reply_text(
            "⛔ Fitur ini khusus Owner."
        )
        return False
    return True


# ============================================================
# MENU
# ============================================================

def main_menu(user_id: int):
    rows = [
        [
            InlineKeyboardButton("🔇 FORCE RANK", callback_data="force_rank"),
            InlineKeyboardButton("🔊 UNFORCE", callback_data="unforce_rank"),
        ],
        [
            InlineKeyboardButton("📋 DAFTAR FORCE", callback_data="force_list"),
        ],
        [
            InlineKeyboardButton("🔗 LINK RANK", callback_data="link_rank"),
            InlineKeyboardButton("⚙️ PENGATURAN", callback_data="settings"),
        ],
        [
            InlineKeyboardButton("❓ BANTUAN", callback_data="help"),
        ],
        [
            InlineKeyboardButton("💰 BUY AKSES BOT", callback_data="buy_access"),
        ],
    ]

    if is_owner(user_id):
        rows.append([
            InlineKeyboardButton("👑 OWNER PANEL", callback_data="owner_panel")
        ])

    return InlineKeyboardMarkup(rows)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.init_db()

    if update.effective_chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        db.save_seen_user(
            update.effective_chat.id,
            user.id,
            user.username,
            user.full_name,
        )

    text = (
        f"🤖 <b>FORCE RANK BOT</b>\n\n"
        f"Halo {user.mention_html()}!\n\n"
        "Gunakan tombol di bawah agar tidak perlu mengetik "
        "command terus-menerus."
    )

    await update.effective_message.reply_text(
        text,
        reply_markup=main_menu(user.id),
        parse_mode="HTML",
    )


# ============================================================
# BUY ACCESS - SEMUA ORANG BOLEH AKSES
# ============================================================

async def buy_access_callback(update: Update, context):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton("🟢 7 HARI", callback_data="buy_7d"),
            InlineKeyboardButton("🔵 30 HARI", callback_data="buy_30d"),
        ],
        [
            InlineKeyboardButton("🟣 90 HARI", callback_data="buy_90d"),
        ],
        [
            InlineKeyboardButton(
                "👑 HUBUNGI OWNER",
                url=f"https://t.me/{os.getenv('OWNER_USERNAME', 'USERNAME_OWNER').lstrip('@')}",
            )
        ],
        [
            InlineKeyboardButton("🔙 KEMBALI", callback_data="back_menu")
        ],
    ]

    text = (
        "💰 <b>BUY AKSES FORCE RANK BOT</b>\n\n"
        "Gunakan bot Force Rank untuk grup kamu.\n\n"
        "📦 Pilih masa aktif:\n\n"
        "🟢 7 Hari\n"
        "🔵 30 Hari\n"
        "🟣 90 Hari\n\n"
        "Setelah pembayaran dikonfirmasi, owner akan "
        "mengaktifkan akses ke akun Telegram kamu.\n\n"
        "👇 Pilih paket yang kamu inginkan."
    )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def buy_package_callback(update: Update, context):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    packages = {
        "buy_7d": "7 Hari",
        "buy_30d": "30 Hari",
        "buy_90d": "90 Hari",
    }
    package = packages.get(query.data)
    if not package:
        return

    owner_username = os.getenv(
        "OWNER_USERNAME", "USERNAME_OWNER"
    ).lstrip("@")

    text = (
        "🛒 <b>PERMINTAAN PEMBELIAN</b>\n\n"
        f"👤 Nama: {user.full_name}\n"
        f"🆔 User ID: <code>{user.id}</code>\n"
        f"💎 Username: @{user.username or '-'}\n\n"
        f"📦 Paket: <b>{package}</b>\n\n"
        "Silakan hubungi owner untuk pembayaran.\n"
        "Setelah pembayaran dikonfirmasi, owner akan "
        "mengaktifkan akses kamu."
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "👑 HUBUNGI OWNER",
                url=f"https://t.me/{owner_username}",
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 KEMBALI",
                callback_data="buy_access",
            )
        ],
    ]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


# ============================================================
# OWNER: AKTIFKAN USER
# ============================================================

async def aktif(update: Update, context):
    if not await owner_required(update):
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Format:\n"
            "/aktif 30d @username\n\n"
            "Contoh:\n"
            "/aktif 30d @alceea"
        )
        return

    duration = args[0]
    target_username = args[1].lstrip("@")

    days = duration_to_days(duration)
    if days is None:
        await update.message.reply_text(
            "❌ Durasi salah.\n\n"
            "Contoh: 30d, 7d, 24h, 30m"
        )
        return

    # Coba cari user dari database yang pernah dikenal bot.
    target = None
    # Search across seen_users is intentionally not exposed in basedata;
    # use a direct DB lookup here for username.
    import sqlite3
    conn = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT user_id, username, name FROM seen_users "
        "WHERE lower(username)=? ORDER BY last_seen DESC LIMIT 1",
        (target_username.lower(),),
    ).fetchone()
    conn.close()

    if not row:
        await update.message.reply_text(
            "❌ Username belum dikenal bot.\n\n"
            "Minta user mengirim /start ke bot terlebih dahulu, "
            "lalu jalankan /aktif lagi."
        )
        return

    user_id = row["user_id"]
    expires = db.add_or_extend_access(
        user_id,
        row["username"],
        row["name"],
        days,
    )

    await update.message.reply_text(
        "✅ <b>AKUN BERHASIL DIAKTIFKAN</b>\n\n"
        f"👤 User ID: <code>{user_id}</code>\n"
        f"💎 Username: @{row['username'] or '-'}\n"
        f"⏳ Durasi: {duration}\n"
        f"📅 Berakhir: {format_expiry(expires.isoformat())}",
        parse_mode="HTML",
    )

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "🎉 <b>AKSES FORCE RANK AKTIF</b>\n\n"
                f"⏳ Durasi: {duration}\n"
                f"📅 Berakhir: {format_expiry(expires.isoformat())}\n\n"
                "Sekarang kamu bisa menambahkan bot ke grup "
                "dan menggunakan fitur Force Rank."
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass


async def nonaktif(update: Update, context):
    if not await owner_required(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Format:\n/nonaktif @username"
        )
        return

    username = context.args[0].lstrip("@").lower()
    import sqlite3
    conn = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT user_id FROM seen_users WHERE lower(username)=? "
        "ORDER BY last_seen DESC LIMIT 1",
        (username,),
    ).fetchone()
    conn.close()

    if not row:
        await update.message.reply_text("❌ User tidak ditemukan.")
        return

    db.remove_access(row["user_id"])
    await update.message.reply_text(
        f"✅ Akses @{username} berhasil dinonaktifkan."
    )


async def status(update: Update, context):
    target_id = update.effective_user.id
    if context.args and is_owner(update.effective_user.id):
        username = context.args[0].lstrip("@").lower()
        import sqlite3
        conn = sqlite3.connect(db.DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT user_id FROM seen_users WHERE lower(username)=? "
            "ORDER BY last_seen DESC LIMIT 1",
            (username,),
        ).fetchone()
        conn.close()
        if row:
            target_id = row["user_id"]

    access = db.get_access(target_id)
    if not access:
        await update.effective_message.reply_text(
            "🔒 Akses belum aktif."
        )
        return

    active = db.has_active_access(target_id)
    await update.effective_message.reply_text(
        "🟢 <b>AKTIF</b>" if active else "🔴 <b>EXPIRED</b>"
        + "\n\n"
        f"🆔 User ID: <code>{target_id}</code>\n"
        f"💎 Username: @{access.get('username') or '-'}\n"
        f"📅 Berakhir: {format_expiry(access['expires_at'])}",
        parse_mode="HTML",
    )


async def daftar_user(update: Update, context):
    if not await owner_required(update):
        return

    rows = db.list_access()
    if not rows:
        await update.message.reply_text("📋 Belum ada user aktif.")
        return

    lines = ["👥 <b>DAFTAR AKSES</b>\n"]
    for i, row in enumerate(rows, 1):
        active = db.has_active_access(row["user_id"])
        lines.append(
            f"{i}. @{row['username'] or '-'} "
            f"| {'🟢' if active else '🔴'} "
            f"| {format_expiry(row['expires_at'])}"
        )

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
    )


# ============================================================
# TARGET RESOLUTION
# ============================================================

async def get_target_from_command(update, context):
    message = update.effective_message

    # 1. Reply = paling akurat
    if message.reply_to_message:
        target = message.reply_to_message.from_user
        if target and not target.is_bot:
            return target

    # 2. @username yang pernah terlihat bot di grup
    if context.args:
        raw = context.args[0]
        if raw.startswith("@"):
            found = db.find_seen_user(
                update.effective_chat.id,
                raw,
            )
            if found:
                class SimpleUser:
                    pass
                u = SimpleUser()
                u.id = found["user_id"]
                u.username = found["username"]
                u.full_name = found["name"]
                u.is_bot = False
                return u

    return None


# ============================================================
# FORCE RANK
# ============================================================

def force_keyboard(chat_id, user_id, cfg):
    rank_link = cfg.get("rank_link")
    sub_channel = cfg.get("sub_channel")

    join_url = sub_channel
    if sub_channel and sub_channel.startswith("@"):
        join_url = f"https://t.me/{sub_channel[1:]}"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📝 ISI RANK",
                url=rank_link
            )
        ],
        [
            InlineKeyboardButton(
                "📢 JOIN CHANNEL",
                url=join_url
            )
        ],
        [
            InlineKeyboardButton(
                "✅ SAYA SUDAH JOIN",
                callback_data=f"check_force:{chat_id}:{user_id}"
            )
        ],
    ])


async def forcerank(update: Update, context):
    user = update.effective_user

    if not await active_required(update, context):
        return

    if not await admin_required(update, context):
        return

    target = await get_target_from_command(update, context)

    if not target:
        await update.message.reply_text(
            "❌ Target tidak ditemukan.\n\n"
            "Gunakan:\n"
            "• Reply pesan user lalu /forcerank\n"
            "• /forcerank @username (user harus pernah terlihat bot)"
        )
        return

    if target.id == user.id:
        await update.message.reply_text(
            "❌ Kamu tidak bisa Force Rank diri sendiri."
        )
        return

    if target.is_bot:
        await update.message.reply_text(
            "❌ Tidak bisa Force Rank bot."
        )
        return

    ready, cfg = group_config_ready(update.effective_chat.id)
    if not ready:
        await update.message.reply_text(
            "⚠️ Konfigurasi belum lengkap.\n\n" + cfg
        )
        return

    chat_id = update.effective_chat.id

    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target.id,
            permissions=ChatPermissions(
                can_send_messages=False
            ),
        )
    except Exception as e:
        logger.exception("Mute gagal: %s", e)
        await update.message.reply_text(
            "❌ Gagal mute user.\n\n"
            "Pastikan bot adalah admin grup dan punya izin "
            "membatasi member."
        )
        return

    db.save_seen_user(
        chat_id,
        target.id,
        target.username,
        target.full_name,
    )
    db.add_force(
        chat_id,
        target.id,
        target.username,
        target.full_name,
    )

    text = (
        "🔔 <b>FORCE RANK</b>\n\n"
        f"👤 User: {target.full_name}\n"
        f"💎 Username: @{target.username or '-'}\n\n"
        "🔇 Status: <b>MUTED</b>\n"
        "📝 Rank: <b>BELUM DIISI</b>\n\n"
        "Silakan isi rank terlebih dahulu.\n"
        "Setelah rank selesai dan sudah subscribe, "
        "mute akan dibuka otomatis."
    )

    await update.message.reply_text(
        text,
        reply_markup=force_keyboard(
            chat_id,
            target.id,
            cfg
        ),
        parse_mode="HTML",
    )

    try:
        await context.bot.send_message(
            chat_id=target.id,
            text=(
                "🔔 <b>KAMU TERKENA FORCE RANK</b>\n\n"
                f"Grup: {update.effective_chat.title}\n\n"
                "Silakan isi rank dan subscribe channel.\n"
                "Setelah dua syarat terpenuhi, kamu akan "
                "di-unmute otomatis."
            ),
            reply_markup=force_keyboard(
                chat_id,
                target.id,
                cfg
            ),
            parse_mode="HTML",
        )
    except Exception:
        # Telegram tidak mengizinkan bot mengirim DM jika user
        # belum pernah start bot.
        pass


async def unforcerank(update: Update, context):
    if not await active_required(update, context):
        return

    if not await admin_required(update, context):
        return

    target = await get_target_from_command(update, context)

    if not target:
        await update.message.reply_text(
            "❌ Target tidak ditemukan.\n"
            "Gunakan reply atau @username."
        )
        return

    chat_id = update.effective_chat.id
    row = db.get_force(chat_id, target.id)

    if not row:
        await update.message.reply_text(
            "⚠️ User tersebut tidak sedang terkena Force Rank."
        )
        return

    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
    except Exception as e:
        logger.exception("Unmute gagal: %s", e)
        await update.message.reply_text(
            "❌ Gagal membuka mute. Pastikan bot admin."
        )
        return

    db.remove_force(chat_id, target.id)

    await update.message.reply_text(
        f"🔓 <b>UNFORCE BERHASIL</b>\n\n"
        f"👤 User: {target.full_name}\n"
        f"💎 Username: @{target.username or '-'}\n\n"
        "User sudah di-unmute.",
        parse_mode="HTML",
    )


async def force_list(update: Update, context):
    if not await active_required(update, context):
        return

    if not await admin_required(update, context):
        return

    rows = db.list_forced(update.effective_chat.id)

    if not rows:
        await update.message.reply_text(
            "📋 Tidak ada member yang sedang Force Rank."
        )
        return

    lines = ["📋 <b>DAFTAR FORCE RANK</b>\n"]

    for i, row in enumerate(rows, 1):
        rank = "✅" if row["rank_filled"] else "❌"
        sub = "✅" if row["subscribed"] else "❌"

        lines.append(
            f"{i}. @{row['username'] or row['name']}\n"
            f"   📝 Rank: {rank}\n"
            f"   📢 Subscribe: {sub}"
        )

    await update.message.reply_text(
        "\n\n".join(lines),
        parse_mode="HTML",
    )


# ============================================================
# SUBSCRIBE CHECK + AUTO UNMUTE
# ============================================================

async def check_subscription(context, channel, user_id):
    if not channel:
        return False

    try:
        member = await context.bot.get_chat_member(
            chat_id=channel,
            user_id=user_id,
        )
        return member.status in (
            "member",
            "administrator",
            "creator",
        )
    except Exception as e:
        logger.warning(
            "Cek subscribe gagal channel=%s user=%s: %s",
            channel,
            user_id,
            e,
        )
        return False


async def try_auto_unmute(chat_id, user_id, context):
    row = db.get_force(chat_id, user_id)
    if not row:
        return False

    cfg = db.get_group(chat_id)
    if not cfg:
        return False

    subscribed = await check_subscription(
        context,
        cfg.get("sub_channel"),
        user_id,
    )

    if subscribed:
        db.set_subscribed(chat_id, user_id, True)

    row = db.get_force(chat_id, user_id)
    if not row:
        return False

    if not row["rank_filled"] or not row["subscribed"]:
        return False

    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
    except Exception as e:
        logger.exception("AUTO UNMUTE gagal: %s", e)
        return False

    username = row["username"]
    display = f"@{username}" if username else row["name"]

    db.remove_force(chat_id, user_id)

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "🔔 <b>FORCE RANK SELESAI</b>\n\n"
            f"👤 User: {display}\n\n"
            "✅ Rank: SUDAH DIISI\n"
            "✅ Subscribe: SUDAH\n\n"
            "🔓 Status: <b>OTOMATIS DI-UNMUTE</b>"
        ),
        parse_mode="HTML",
    )

    return True


async def check_force_callback(update: Update, context):
    query = update.callback_query

    try:
        _, chat_id_raw, target_id_raw = query.data.split(":")
        chat_id = int(chat_id_raw)
        target_id = int(target_id_raw)
    except Exception:
        await query.answer("❌ Data tombol tidak valid.", show_alert=True)
        return

    if query.from_user.id != target_id:
        await query.answer(
            "❌ Tombol ini bukan untuk kamu.",
            show_alert=True,
        )
        return

    row = db.get_force(chat_id, target_id)
    if not row:
        await query.answer(
            "⚠️ Kamu tidak sedang terkena Force Rank.",
            show_alert=True,
        )
        return

    cfg = db.get_group(chat_id)
    if not cfg:
        await query.answer(
            "❌ Konfigurasi grup tidak ditemukan.",
            show_alert=True,
        )
        return

    subscribed = await check_subscription(
        context,
        cfg.get("sub_channel"),
        target_id,
    )

    if subscribed:
        db.set_subscribed(chat_id, target_id, True)

    row = db.get_force(chat_id, target_id)

    if not row["rank_filled"]:
        await query.answer(
            "❌ Rank belum terdeteksi. Silakan komentar di post rank.",
            show_alert=True,
        )
        return

    if not row["subscribed"]:
        await query.answer(
            "❌ Kamu belum subscribe channel.",
            show_alert=True,
        )
        return

    done = await try_auto_unmute(
        chat_id,
        target_id,
        context,
    )

    if done:
        await query.edit_message_text(
            "🎉 <b>FORCE RANK SELESAI</b>\n\n"
            "✅ Rank sudah diisi\n"
            "✅ Sudah subscribe\n"
            "🔓 Kamu telah di-unmute otomatis.",
            parse_mode="HTML",
        )
    else:
        await query.answer(
            "⚠️ Syarat belum lengkap atau bot gagal unmute.",
            show_alert=True,
        )


# ============================================================
# DETEKSI KOMENTAR RANK
# ============================================================

def is_rank_comment(message, cfg):
    """
    Komentar channel biasanya masuk ke linked discussion group.
    Bot mendeteksi reply ke automatic-forward dari post channel.
    """
    if not cfg or not cfg.get("rank_link"):
        return False

    channel, post_id = parse_rank_link(cfg["rank_link"])
    if not channel or not post_id:
        return False

    parent = message.reply_to_message
    if not parent:
        return False

    # Bot API modern: MessageOriginChannel
    origin = getattr(parent, "forward_origin", None)

    if origin:
        origin_chat = getattr(origin, "chat", None)
        origin_message_id = getattr(origin, "message_id", None)

        if origin_chat and origin_message_id:
            origin_id = getattr(origin_chat, "id", None)
            origin_username = getattr(origin_chat, "username", None)

            channel_match = False

            if str(channel).startswith("-100"):
                try:
                    channel_match = origin_id == int(channel)
                except Exception:
                    pass
            else:
                channel_match = (
                    origin_username
                    and origin_username.lower()
                    == str(channel).lstrip("@").lower()
                )

            return channel_match and origin_message_id == post_id

    return False


async def rank_comment_handler(update: Update, context):
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not user:
        return

    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    db.save_seen_user(
        chat.id,
        user.id,
        user.username,
        user.full_name,
    )

    # Komentar hanya ditandai jika user memang sedang di-force
    rows = db.list_forced(chat.id)

    # Discussion group adalah chat yang berbeda dari grup tempat user
    # di-mute. Karena itu handler di bawah juga menangani lewat mapping
    # rank_channel jika dikonfigurasi. Untuk komentar langsung di grup
    # diskusi, pencarian semua force aktif digunakan.
    for row in rows:
        cfg = db.get_group(row["chat_id"])
        if not cfg:
            continue

        if is_rank_comment(message, cfg):
            db.set_rank_filled(
                row["chat_id"],
                user.id,
                True,
            )
            await try_auto_unmute(
                row["chat_id"],
                user.id,
                context,
            )
            return


# ============================================================
# SET RANK / SUBSCRIBE
# ============================================================

async def setrank(update: Update, context):
    if not await active_required(update, context):
        return
    if not await admin_required(update, context):
        return

    if not context.args:
        await update.message.reply_text(
            "📌 Kirim link post rank.\n\n"
            "Contoh:\n"
            "/setrank https://t.me/channel/9"
        )
        return

    link = context.args[0]
    channel, post_id = parse_rank_link(link)

    if not channel:
        await update.message.reply_text(
            "❌ Link rank tidak valid.\n\n"
            "Contoh:\n"
            "https://t.me/abshsjjjv/9"
        )
        return

    db.save_group(
        update.effective_chat.id,
        title=update.effective_chat.title,
        updated_by=update.effective_user.id,
        rank_link=link,
        rank_channel=channel,
        rank_post_id=post_id,
    )

    await update.message.reply_text(
        "✅ <b>LINK RANK DISIMPAN</b>\n\n"
        f"🔗 {link}",
        parse_mode="HTML",
    )


async def setsub(update: Update, context):
    if not await active_required(update, context):
        return
    if not await admin_required(update, context):
        return

    if not context.args:
        await update.message.reply_text(
            "📢 Kirim username/link channel.\n\n"
            "Contoh:\n"
            "/setsub @channelkamu"
        )
        return

    channel = normalize_channel(context.args[0])

    db.save_group(
        update.effective_chat.id,
        title=update.effective_chat.title,
        updated_by=update.effective_user.id,
        sub_channel=channel,
    )

    await update.message.reply_text(
        "✅ <b>CHANNEL WAJIB SUBSCRIBE DISIMPAN</b>\n\n"
        f"📢 {channel}",
        parse_mode="HTML",
    )


async def config_info(update: Update, context):
    if not await active_required(update, context):
        return
    if not await admin_required(update, context):
        return

    cfg = db.get_group(update.effective_chat.id)

    if not cfg:
        await update.message.reply_text(
            "⚙️ Belum ada konfigurasi."
        )
        return

    await update.message.reply_text(
        "⚙️ <b>KONFIGURASI FORCE RANK</b>\n\n"
        f"🔗 Rank: {cfg.get('rank_link') or '-'}\n"
        f"📢 Subscribe: {cfg.get('sub_channel') or '-'}",
        parse_mode="HTML",
    )


# ============================================================
# BUTTON CALLBACK MENU
# ============================================================

async def menu_callback(update: Update, context):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    if data == "back_menu":
        await query.answer()
        await query.edit_message_text(
            "🤖 <b>FORCE RANK BOT</b>\n\n"
            "Gunakan tombol di bawah.",
            reply_markup=main_menu(user_id),
            parse_mode="HTML",
        )
        return

    if data == "buy_access":
        await buy_access_callback(update, context)
        return

    if data in ("buy_7d", "buy_30d", "buy_90d"):
        await buy_package_callback(update, context)
        return

    await query.answer()

    if data == "force_rank":
        await query.message.reply_text(
            "🔇 <b>FORCE RANK</b>\n\n"
            "Reply pesan member dengan:\n"
            "<code>/forcerank</code>\n\n"
            "atau:\n"
            "<code>/forcerank @username</code>",
            parse_mode="HTML",
        )

    elif data == "unforce_rank":
        await query.message.reply_text(
            "🔊 <b>UNFORCE</b>\n\n"
            "Reply pesan member dengan:\n"
            "<code>/unforcerank</code>\n\n"
            "atau:\n"
            "<code>/unforcerank @username</code>",
            parse_mode="HTML",
        )

    elif data == "force_list":
        if await active_required(update, context):
            if await admin_required(update, context):
                rows = db.list_forced(query.message.chat.id)
                if not rows:
                    await query.message.reply_text(
                        "📋 Tidak ada member yang sedang Force Rank."
                    )
                else:
                    lines = ["📋 <b>DAFTAR FORCE RANK</b>\n"]
                    for i, row in enumerate(rows, 1):
                        lines.append(
                            f"{i}. @{row['username'] or row['name']}\n"
                            f"📝 Rank: {'✅' if row['rank_filled'] else '❌'}\n"
                            f"📢 Subs: {'✅' if row['subscribed'] else '❌'}"
                        )
                    await query.message.reply_text(
                        "\n\n".join(lines),
                        parse_mode="HTML",
                    )

    elif data == "link_rank":
        if await active_required(update, context):
            await query.message.reply_text(
                "🔗 <b>LINK RANK</b>\n\n"
                "Admin grup dapat mengatur dengan:\n"
                "<code>/setrank https://t.me/channel/9</code>",
                parse_mode="HTML",
            )

    elif data == "settings":
        if await active_required(update, context):
            await query.message.reply_text(
                "⚙️ <b>PENGATURAN</b>\n\n"
                "/setrank - atur link rank\n"
                "/setsub - atur channel wajib subscribe\n"
                "/config - lihat konfigurasi",
                parse_mode="HTML",
            )

    elif data == "help":
        await query.message.reply_text(
            "❓ <b>BANTUAN</b>\n\n"
            "🔇 /forcerank - mute + wajib rank\n"
            "🔊 /unforcerank - buka force\n"
            "📋 /forcelist - daftar force\n"
            "🔗 /setrank - link rank\n"
            "📢 /setsub - channel wajib subscribe\n"
            "⚙️ /config - konfigurasi\n"
            "💰 /start → Buy Akses Bot",
            parse_mode="HTML",
        )

    elif data == "owner_panel":
        if not is_owner(user_id):
            await query.message.reply_text("⛔ Khusus Owner.")
            return

        await query.message.reply_text(
            "👑 <b>OWNER PANEL</b>\n\n"
            "/aktif 30d @username\n"
            "/nonaktif @username\n"
            "/status @username\n"
            "/users",
            parse_mode="HTML",
        )


# ============================================================
# TRACK USER
# ============================================================

async def track_user(update: Update, context):
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not user:
        return

    if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        db.save_seen_user(
            chat.id,
            user.id,
            user.username,
            user.full_name,
        )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(update, context):
    logger.exception(
        "Unhandled exception",
        exc_info=context.error,
    )


# ============================================================
# MAIN
# ============================================================

def main():
    db.init_db()

    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )

    # Public commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", start))
    application.add_handler(CommandHandler("buy", buy_access_callback))
    application.add_handler(CommandHandler("status", status))

    # Owner
    application.add_handler(CommandHandler("aktif", aktif))
    application.add_handler(CommandHandler("nonaktif", nonaktif))
    application.add_handler(CommandHandler("users", daftar_user))

    # Group Force Rank
    application.add_handler(CommandHandler("forcerank", forcerank))
    application.add_handler(CommandHandler("unforcerank", unforcerank))
    application.add_handler(CommandHandler("unforcer", unforcerank))
    application.add_handler(CommandHandler("forcelist", force_list))

    # Configuration
    application.add_handler(CommandHandler("setrank", setrank))
    application.add_handler(CommandHandler("setsub", setsub))
    application.add_handler(CommandHandler("config", config_info))

    # Buttons
    application.add_handler(
        CallbackQueryHandler(
            check_force_callback,
            pattern=r"^check_force:-?\d+:\d+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            buy_access_callback,
            pattern=r"^buy_access$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            buy_package_callback,
            pattern=r"^buy_(7d|30d|90d)$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(menu_callback)
    )

    # Track users and detect rank comments.
    # Commands are processed before this handler.
    application.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND,
            rank_comment_handler,
        ),
        group=1,
    )
    application.add_handler(
        MessageHandler(
            filters.ALL,
            track_user,
        ),
        group=2,
    )

    application.add_error_handler(error_handler)

    logger.info("FORCE RANK BOT sedang berjalan...")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=False,
    )


if __name__ == "__main__":
    main()
