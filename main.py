# main.py
# FORCE RANK BOT - Railway ready
# python-telegram-bot 21.x
#
# ENV:
# BOT_TOKEN=...
# OWNER_ID=...
# OWNER_ID_2=...          (optional)
# OWNER_USERNAME=...      (optional)
#
# Rank flow:
# 1) Admin /forcerank @user or reply /forcerank
# 2) User is muted
# 3) Bot posts ISI RANK + JOIN CHANNEL + SAYA SUDAH JOIN
# 4) User comments on the configured rank post in its discussion group
# 5) Bot marks rank_filled
# 6) Bot checks subscription
# 7) When BOTH are complete, bot automatically unmutes.
#
# IMPORTANT:
# - Bot must be admin in the main group with permission to restrict members.
# - Bot must be able to access the subscription channel and should be admin there
#   for reliable get_chat_member checks.
# - The channel must have a linked discussion group for comments.
# - Configure the rank post with /setrank https://t.me/channel/POST_ID
# - Configure subscription with /setsub @channel

import os
import re
import logging
import sqlite3
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

def env_int(name, default=0):
    try:
        return int(os.getenv(name, str(default)).strip())
    except (ValueError, TypeError):
        return default

OWNER_ID = env_int("OWNER_ID")
OWNER_ID_2 = env_int("OWNER_ID_2")
OWNER_IDS = {x for x in (OWNER_ID, OWNER_ID_2) if x}

OWNER_USERNAME = os.getenv("OWNER_USERNAME", "").strip().lstrip("@")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN belum diisi di Railway Variables.")
if not OWNER_IDS:
    raise RuntimeError("OWNER_ID belum diisi di Railway Variables.")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("forcerank")


# ============================================================
# GENERAL HELPERS
# ============================================================

def is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS


def display_user(user) -> str:
    if getattr(user, "username", None):
        return f"@{user.username}"
    return getattr(user, "full_name", "User")


def format_expiry(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime("%d-%m-%Y %H:%M UTC")
    except Exception:
        return value


def duration_to_days(value: str):
    m = re.fullmatch(r"(\d+)\s*([dhm])", value.lower().strip())
    if not m:
        return None
    amount = int(m.group(1))
    if amount <= 0:
        return None
    unit = m.group(2)
    if unit == "d":
        return float(amount)
    if unit == "h":
        return amount / 24
    return amount / 1440


def parse_rank_link(link: str):
    """
    Returns (channel_identifier, post_id).

    Public:
      https://t.me/channelname/9 -> ("channelname", 9)

    Private:
      https://t.me/c/1234567890/9 -> ("-1001234567890", 9)
    """
    link = link.strip()

    m = re.match(
        r"^https?://t\.me/c/(\d+)/(\d+)(?:\?.*)?$",
        link,
        re.I,
    )
    if m:
        return f"-100{m.group(1)}", int(m.group(2))

    m = re.match(
        r"^https?://t\.me/([^/]+)/(\d+)(?:\?.*)?$",
        link,
        re.I,
    )
    if m:
        return m.group(1).lstrip("@"), int(m.group(2))

    return None, None


def normalize_channel(value: str):
    value = value.strip()

    if value.startswith("https://t.me/"):
        value = value.replace("https://t.me/", "", 1)
        value = value.split("/")[0]

    if value.startswith("t.me/"):
        value = value.replace("t.me/", "", 1)
        value = value.split("/")[0]

    return value


def group_config_ready(chat_id):
    cfg = db.get_group(chat_id)

    if not cfg:
        return False, "Konfigurasi grup belum dibuat."

    if not cfg.get("rank_link"):
        return False, "Link rank belum diatur. Gunakan /setrank."

    if not cfg.get("rank_channel") or not cfg.get("rank_post_id"):
        return False, "Link rank tidak memiliki channel/post ID yang valid."

    if not cfg.get("sub_channel"):
        return False, "Channel wajib subscribe belum diatur. Gunakan /setsub."

    return True, cfg


# ============================================================
# ACCESS CONTROL
# ============================================================

async def active_required(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if is_owner(user.id):
        return True

    if db.has_active_access(user.id):
        return True

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "💰 BUY AKSES BOT",
            callback_data="buy_access"
        )]
    ])

    if update.callback_query:
        await update.callback_query.answer(
            "🔒 Akses kamu belum aktif.",
            show_alert=True,
        )
        await update.callback_query.message.reply_text(
            "🔒 <b>AKSES BELUM AKTIF</b>\n\n"
            "Akun kamu belum memiliki akses Force Rank.\n"
            "Silakan beli akses terlebih dahulu.",
            reply_markup=markup,
            parse_mode="HTML",
        )
    else:
        await update.effective_message.reply_text(
            "🔒 <b>AKSES BELUM AKTIF</b>\n\n"
            "Akun kamu belum memiliki akses Force Rank.\n"
            "Silakan beli akses terlebih dahulu.",
            reply_markup=markup,
            parse_mode="HTML",
        )
    return False


async def admin_required(update: Update, context, user_id=None):
    chat = update.effective_chat
    uid = user_id or update.effective_user.id

    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await update.effective_message.reply_text(
            "❌ Perintah ini hanya bisa digunakan di grup."
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
            "Pastikan bot adalah admin grup."
        )
        return False


async def owner_required(update: Update):
    if not is_owner(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Fitur ini khusus Owner.")
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
    db.init_db()
    user = update.effective_user

    if update.effective_chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        db.save_seen_user(
            update.effective_chat.id,
            user.id,
            user.username,
            user.full_name,
        )

    await update.effective_message.reply_text(
        f"🤖 <b>FORCE RANK BOT</b>\n\n"
        f"Halo {user.mention_html()}!\n\n"
        "Pilih menu di bawah.",
        reply_markup=main_menu(user.id),
        parse_mode="HTML",
    )


# ============================================================
# BUY ACCESS - PUBLIC
# ============================================================

def buy_keyboard():
    owner_url = (
        f"https://t.me/{OWNER_USERNAME}"
        if OWNER_USERNAME
        else "https://t.me/"
    )

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 7 HARI", callback_data="buy_7d"),
            InlineKeyboardButton("🔵 30 HARI", callback_data="buy_30d"),
        ],
        [
            InlineKeyboardButton("🟣 90 HARI", callback_data="buy_90d"),
        ],
        [
            InlineKeyboardButton("👑 HUBUNGI OWNER", url=owner_url),
        ],
        [
            InlineKeyboardButton("🔙 KEMBALI", callback_data="back_menu"),
        ],
    ])


async def show_buy_access(query):
    await query.edit_message_text(
        "💰 <b>BUY AKSES FORCE RANK BOT</b>\n\n"
        "Semua orang bisa membuka halaman ini.\n\n"
        "📦 Pilih masa aktif:\n\n"
        "🟢 7 Hari\n"
        "🔵 30 Hari\n"
        "🟣 90 Hari\n\n"
        "Setelah pembayaran dikonfirmasi, owner "
        "akan mengaktifkan akses ke akun Telegram kamu.",
        reply_markup=buy_keyboard(),
        parse_mode="HTML",
    )


async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💰 <b>BUY AKSES FORCE RANK BOT</b>\n\n"
        "Pilih paket di bawah:",
        reply_markup=buy_keyboard(),
        parse_mode="HTML",
    )


async def buy_package_callback(update: Update, context):
    query = update.callback_query
    await query.answer()

    package = {
        "buy_7d": "7 Hari",
        "buy_30d": "30 Hari",
        "buy_90d": "90 Hari",
    }.get(query.data)

    if not package:
        return

    user = query.from_user
    owner_url = (
        f"https://t.me/{OWNER_USERNAME}"
        if OWNER_USERNAME
        else "https://t.me/"
    )

    await query.edit_message_text(
        "🛒 <b>PERMINTAAN PEMBELIAN</b>\n\n"
        f"👤 Nama: {user.full_name}\n"
        f"🆔 User ID: <code>{user.id}</code>\n"
        f"💎 Username: @{user.username or '-'}\n\n"
        f"📦 Paket: <b>{package}</b>\n\n"
        "Hubungi owner untuk pembayaran.\n"
        "Setelah pembayaran dikonfirmasi, owner akan "
        "mengaktifkan akses kamu.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👑 HUBUNGI OWNER", url=owner_url)],
            [InlineKeyboardButton("🔙 KEMBALI", callback_data="buy_access")],
        ]),
        parse_mode="HTML",
    )


# ============================================================
# OWNER ACCESS
# ============================================================

def find_user_by_username(username):
    return db.find_access_user_by_username(username)


async def aktif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await owner_required(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Format:\n/aktif 30d @username\n\n"
            "Contoh:\n/aktif 30d @alceea"
        )
        return

    duration = context.args[0]
    username = context.args[1].lstrip("@")
    days = duration_to_days(duration)

    if days is None:
        await update.message.reply_text(
            "❌ Durasi salah. Contoh: 30d, 7d, 24h, 30m"
        )
        return

    target = find_user_by_username(username)

    if not target:
        await update.message.reply_text(
            "❌ Username belum dikenal bot.\n\n"
            "Minta pembeli membuka /start ke bot terlebih dahulu, "
            "lalu jalankan /aktif lagi."
        )
        return

    expires = db.add_or_extend_access(
        target["user_id"],
        target["username"],
        target["name"],
        days,
    )

    await update.message.reply_text(
        "✅ <b>AKUN BERHASIL DIAKTIFKAN</b>\n\n"
        f"👤 User ID: <code>{target['user_id']}</code>\n"
        f"💎 Username: @{target['username'] or '-'}\n"
        f"⏳ Durasi: {duration}\n"
        f"📅 Berakhir: {format_expiry(expires.isoformat())}",
        parse_mode="HTML",
    )

    try:
        await context.bot.send_message(
            target["user_id"],
            "🎉 <b>AKSES FORCE RANK AKTIF</b>\n\n"
            f"⏳ Durasi: {duration}\n"
            f"📅 Berakhir: {format_expiry(expires.isoformat())}\n\n"
            "Sekarang kamu bisa menambahkan bot ke grup "
            "dan menggunakan fitur Force Rank.",
            parse_mode="HTML",
        )
    except Exception:
        pass


async def nonaktif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await owner_required(update):
        return

    if not context.args:
        await update.message.reply_text("Format: /nonaktif @username")
        return

    target = find_user_by_username(context.args[0])
    if not target:
        await update.message.reply_text("❌ User tidak ditemukan.")
        return

    db.remove_access(target["user_id"])
    await update.message.reply_text(
        f"✅ Akses @{target['username'] or '-'} dinonaktifkan."
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_id = update.effective_user.id

    if context.args and is_owner(update.effective_user.id):
        target = find_user_by_username(context.args[0])
        if target:
            target_id = target["user_id"]

    access = db.get_access(target_id)
    if not access:
        await update.effective_message.reply_text("🔒 Akses belum aktif.")
        return

    active = db.has_active_access(target_id)
    await update.effective_message.reply_text(
        ("🟢 <b>AKTIF</b>" if active else "🔴 <b>EXPIRED</b>")
        + "\n\n"
        f"🆔 User ID: <code>{target_id}</code>\n"
        f"💎 Username: @{access.get('username') or '-'}\n"
        f"📅 Berakhir: {format_expiry(access['expires_at'])}",
        parse_mode="HTML",
    )


async def daftar_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await owner_required(update):
        return

    rows = db.list_access()
    if not rows:
        await update.message.reply_text("📋 Belum ada akses.")
        return

    lines = ["👥 <b>DAFTAR AKSES</b>\n"]
    for i, row in enumerate(rows, 1):
        lines.append(
            f"{i}. @{row['username'] or '-'} | "
            f"{'🟢' if db.has_active_access(row['user_id']) else '🔴'} | "
            f"{format_expiry(row['expires_at'])}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ============================================================
# TARGET RESOLUTION
# ============================================================

async def get_target_from_command(update, context):
    message = update.effective_message

    if message.reply_to_message:
        target = message.reply_to_message.from_user
        if target and not target.is_bot:
            return target

    if context.args and context.args[0].startswith("@"):
        found = db.find_seen_user(update.effective_chat.id, context.args[0])
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
# FORCE RANK MESSAGE / BUTTONS
# ============================================================

def join_url(channel):
    if not channel:
        return None
    value = str(channel).strip()
    if value.startswith("@"):
        return f"https://t.me/{value[1:]}"
    if re.fullmatch(r"[A-Za-z0-9_]{4,}", value):
        return f"https://t.me/{value}"
    if value.startswith("https://t.me/"):
        return value
    return None


def force_keyboard(chat_id, user_id, cfg):
    rows = []

    # Always show the buttons if /forcerank was allowed.
    if cfg.get("rank_link"):
        rows.append([
            InlineKeyboardButton(
                "📝 ISI RANK",
                url=cfg["rank_link"],
            )
        ])

    sub_url = join_url(cfg.get("sub_channel"))
    if sub_url:
        rows.append([
            InlineKeyboardButton(
                "📢 IKUTI / SUBSCRIBE CHANNEL",
                url=sub_url,
            )
        ])
    else:
        # For private channels, user can still use the check button.
        rows.append([
            InlineKeyboardButton(
                "📢 CHANNEL WAJIB SUBSCRIBE",
                callback_data=f"sub_info:{chat_id}:{user_id}",
            )
        ])

    rows.append([
        InlineKeyboardButton(
            "✅ SAYA SUDAH JOIN",
            callback_data=f"check_force:{chat_id}:{user_id}",
        )
    ])

    return InlineKeyboardMarkup(rows)


async def forcerank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await active_required(update, context):
        return

    if not await admin_required(update, context):
        return

    target = await get_target_from_command(update, context)

    if not target:
        await update.message.reply_text(
            "❌ Target tidak ditemukan.\n\n"
            "Gunakan:\n"
            "• Reply pesan member lalu /forcerank\n"
            "• /forcerank @username\n\n"
            "Untuk @username, user harus pernah terlihat oleh bot."
        )
        return

    if target.id == update.effective_user.id:
        await update.message.reply_text("❌ Tidak bisa Force Rank diri sendiri.")
        return

    if target.is_bot:
        await update.message.reply_text("❌ Tidak bisa Force Rank bot.")
        return

    ready, cfg = group_config_ready(update.effective_chat.id)
    if not ready:
        await update.message.reply_text(
            "⚠️ <b>KONFIGURASI BELUM LENGKAP</b>\n\n"
            f"{cfg}\n\n"
            "Contoh:\n"
            "/setrank https://t.me/abshsjjjv/9\n"
            "/setsub @channelkamu",
            parse_mode="HTML",
        )
        return

    chat_id = update.effective_chat.id

    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target.id,
            permissions=ChatPermissions(can_send_messages=False),
        )
    except Exception as e:
        logger.exception("Mute gagal: %s", e)
        await update.message.reply_text(
            "❌ Gagal mute.\n"
            "Pastikan bot admin dan punya izin membatasi member."
        )
        return

    db.save_seen_user(chat_id, target.id, target.username, target.full_name)
    db.add_force(chat_id, target.id, target.username, target.full_name)

    text = (
        "🔔 <b>FORCE RANK</b>\n\n"
        f"👤 User: {target.full_name}\n"
        f"💎 Username: @{target.username or '-'}\n\n"
        "🔇 Status: <b>MUTED</b>\n"
        "📝 Rank: <b>BELUM DIISI</b>\n"
        "📢 Subscribe: <b>BELUM</b>\n\n"
        "Silakan lakukan kedua syarat di bawah.\n"
        "Setelah rank terisi dan sudah subscribe, "
        "mute akan dibuka otomatis."
    )

    await update.message.reply_text(
        text,
        reply_markup=force_keyboard(chat_id, target.id, cfg),
        parse_mode="HTML",
    )


async def unforcerank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await active_required(update, context):
        return
    if not await admin_required(update, context):
        return

    target = await get_target_from_command(update, context)
    if not target:
        await update.message.reply_text(
            "❌ Target tidak ditemukan. Gunakan reply atau @username."
        )
        return

    chat_id = update.effective_chat.id
    if not db.get_force(chat_id, target.id):
        await update.message.reply_text(
            "⚠️ User tersebut tidak sedang terkena Force Rank."
        )
        return

    if await unmute_user(chat_id, target.id, context, automatic=False):
        await update.message.reply_text(
            f"🔓 <b>UNFORCE BERHASIL</b>\n\n"
            f"👤 {display_user(target)}\n"
            "User sudah di-unmute.",
            parse_mode="HTML",
        )


async def force_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        lines.append(
            f"{i}. @{row['username'] or row['name']}\n"
            f"   📝 Rank: {'✅' if row['rank_filled'] else '❌'}\n"
            f"   📢 Subscribe: {'✅' if row['subscribed'] else '❌'}"
        )

    await update.message.reply_text("\n\n".join(lines), parse_mode="HTML")


# ============================================================
# SUBSCRIBE + UNMUTE
# ============================================================

async def check_subscription(context, channel, user_id):
    if not channel:
        return False

    try:
        member = await context.bot.get_chat_member(
            chat_id=channel,
            user_id=user_id,
        )
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        logger.warning(
            "Cek subscribe gagal: channel=%s user=%s error=%s",
            channel, user_id, e
        )
        return False


async def unmute_user(chat_id, user_id, context, automatic=True):
    row = db.get_force(chat_id, user_id)
    if not row:
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
        logger.exception("Unmute gagal: %s", e)
        return False

    display = f"@{row['username']}" if row["username"] else row["name"]
    db.remove_force(chat_id, user_id)

    if automatic:
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

        cfg = db.get_group(chat_id)
        admin_id = cfg.get("updated_by") if cfg else None
        if admin_id:
            try:
                await context.bot.send_message(
                    admin_id,
                    "🔔 <b>NOTIFIKASI FORCE RANK</b>\n\n"
                    f"👤 {display} telah mengisi rank.\n"
                    "✅ Rank: SUDAH DIISI\n"
                    "✅ Subscribe: SUDAH\n"
                    "🔓 Status: OTOMATIS DI-UNMUTE.",
                    parse_mode="HTML",
                )
            except Exception:
                pass

    return True


async def try_auto_unmute(chat_id, user_id, context):
    row = db.get_force(chat_id, user_id)
    if not row:
        return False

    cfg = db.get_group(chat_id)
    if not cfg:
        return False

    # Refresh subscription every time.
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

    return await unmute_user(chat_id, user_id, context, automatic=True)


async def check_force_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    done = await try_auto_unmute(chat_id, target_id, context)

    if done:
        try:
            await query.edit_message_text(
                "🎉 <b>FORCE RANK SELESAI</b>\n\n"
                "✅ Rank sudah diisi\n"
                "✅ Sudah subscribe\n"
                "🔓 Kamu telah di-unmute otomatis.",
                parse_mode="HTML",
            )
        except Exception:
            pass
        await query.answer("✅ Semua syarat terpenuhi!", show_alert=True)
        return

    row = db.get_force(chat_id, target_id)
    if not row:
        return

    cfg = db.get_group(chat_id)
    subscribed = await check_subscription(
        context,
        cfg.get("sub_channel") if cfg else None,
        target_id,
    )

    if subscribed:
        db.set_subscribed(chat_id, target_id, True)

    row = db.get_force(chat_id, target_id)

    if not row["rank_filled"]:
        await query.answer(
            "❌ Rank belum terdeteksi. Komentari post rank yang diberikan.",
            show_alert=True,
        )
        return

    if not row["subscribed"]:
        await query.answer(
            "❌ Kamu belum subscribe channel wajib.",
            show_alert=True,
        )
        return

    await query.answer(
        "⏳ Syarat sudah lengkap, tetapi bot gagal unmute. Cek izin bot.",
        show_alert=True,
    )


async def sub_info_callback(update, context):
    query = update.callback_query
    await query.answer(
        "📢 Silakan subscribe channel yang sudah ditentukan admin, "
        "lalu tekan SAYA SUDAH JOIN.",
        show_alert=True,
    )


# ============================================================
# RANK COMMENT DETECTION
# ============================================================

def channel_matches(origin_chat, configured_channel):
    if not origin_chat or not configured_channel:
        return False

    configured = str(configured_channel).lstrip("@")
    origin_id = getattr(origin_chat, "id", None)
    origin_username = getattr(origin_chat, "username", None)

    if configured.startswith("-100"):
        try:
            return origin_id == int(configured)
        except ValueError:
            return False

    return bool(
        origin_username
        and origin_username.lower() == configured.lower()
    )


def is_rank_comment(message, cfg):
    """
    A channel comment normally appears in the linked discussion group
    as a reply to the automatic forwarded channel post.

    We match:
      reply_to_message.forward_origin.chat
      reply_to_message.forward_origin.message_id

    Fallbacks are included for older Bot API fields.
    """
    if not message or not cfg:
        return False

    configured_channel = cfg.get("rank_channel")
    configured_post = cfg.get("rank_post_id")

    if not configured_channel or not configured_post:
        return False

    parent = message.reply_to_message
    if not parent:
        return False

    origin = getattr(parent, "forward_origin", None)

    if origin:
        origin_chat = getattr(origin, "chat", None)
        origin_message_id = getattr(origin, "message_id", None)

        if (
            origin_chat
            and origin_message_id == int(configured_post)
            and channel_matches(origin_chat, configured_channel)
        ):
            return True

    # Fallback for older telegram objects.
    old_chat = getattr(parent, "forward_from_chat", None)
    old_message_id = getattr(parent, "forward_from_message_id", None)

    if (
        old_chat
        and old_message_id == int(configured_post)
        and channel_matches(old_chat, configured_channel)
    ):
        return True

    # Another useful fallback: sender_chat on the forwarded discussion parent.
    sender_chat = getattr(parent, "sender_chat", None)
    if (
        sender_chat
        and getattr(parent, "forward_from_message_id", None) == int(configured_post)
        and channel_matches(sender_chat, configured_channel)
    ):
        return True

    return False


async def rank_comment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user

    if not message or not user or user.is_bot:
        return

    # This handler is intentionally allowed in groups/discussion groups.
    # We do NOT assume the discussion group's chat_id equals the main group.
    if update.effective_chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    # Check every active Force Rank record against its configured rank post.
    # This is the key fix compared with the previous version.
    for forced in db.all_forced():
        cfg = db.get_group(forced["chat_id"])
        if not cfg:
            continue

        if not is_rank_comment(message, cfg):
            continue

        # Do not let an unrelated person's comment unlock another user.
        if user.id != forced["user_id"]:
            continue

        db.set_rank_filled(
            forced["chat_id"],
            forced["user_id"],
            True,
        )

        logger.info(
            "Rank terdeteksi: user=%s main_group=%s",
            user.id,
            forced["chat_id"],
        )

        # Immediately try. If user has not subscribed yet, the periodic
        # checker will catch it after they subscribe.
        await try_auto_unmute(
            forced["chat_id"],
            forced["user_id"],
            context,
        )
        return


# ============================================================
# PERIODIC CHECK
# ============================================================

async def periodic_force_check(context: ContextTypes.DEFAULT_TYPE):
    """
    Runs every 20 seconds.
    This makes the system automatic even when:
      - user comments first, then subscribes later
      - user subscribes first, then comments later
    """
    try:
        for forced in db.all_forced():
            await try_auto_unmute(
                forced["chat_id"],
                forced["user_id"],
                context,
            )
    except Exception:
        logger.exception("Periodic Force Rank check error")


# ============================================================
# CONFIGURATION
# ============================================================

async def setrank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await active_required(update, context):
        return
    if not await admin_required(update, context):
        return

    if not context.args:
        await update.message.reply_text(
            "📌 <b>SET LINK RANK</b>\n\n"
            "Contoh:\n"
            "/setrank https://t.me/abshsjjjv/9",
            parse_mode="HTML",
        )
        return

    link = context.args[0]
    channel, post_id = parse_rank_link(link)

    if not channel:
        await update.message.reply_text(
            "❌ Link rank tidak valid.\n\n"
            "Contoh:\nhttps://t.me/abshsjjjv/9"
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
        f"🔗 {link}\n"
        f"📌 Post ID: {post_id}\n\n"
        "Komentar user pada post ini akan digunakan sebagai "
        "tanda rank sudah diisi.",
        parse_mode="HTML",
    )


async def setsub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await active_required(update, context):
        return
    if not await admin_required(update, context):
        return

    if not context.args:
        await update.message.reply_text(
            "📢 <b>SET CHANNEL WAJIB SUBSCRIBE</b>\n\n"
            "Contoh:\n/setsub @channelkamu",
            parse_mode="HTML",
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
        f"📢 {channel}\n\n"
        "Pastikan bot bisa mengakses channel tersebut.",
        parse_mode="HTML",
    )


async def config_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await active_required(update, context):
        return
    if not await admin_required(update, context):
        return

    cfg = db.get_group(update.effective_chat.id)

    if not cfg:
        await update.message.reply_text("⚙️ Belum ada konfigurasi.")
        return

    await update.message.reply_text(
        "⚙️ <b>KONFIGURASI FORCE RANK</b>\n\n"
        f"🔗 Rank: {cfg.get('rank_link') or '-'}\n"
        f"📌 Channel rank: {cfg.get('rank_channel') or '-'}\n"
        f"📌 Post rank: {cfg.get('rank_post_id') or '-'}\n"
        f"📢 Subscribe: {cfg.get('sub_channel') or '-'}",
        parse_mode="HTML",
    )


# ============================================================
# CALLBACK MENU
# ============================================================

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    if data == "back_menu":
        await query.answer()
        await query.edit_message_text(
            "🤖 <b>FORCE RANK BOT</b>\n\nPilih menu:",
            reply_markup=main_menu(user_id),
            parse_mode="HTML",
        )
        return

    if data == "buy_access":
        await query.answer()
        await show_buy_access(query)
        return

    if data in ("buy_7d", "buy_30d", "buy_90d"):
        await buy_package_callback(update, context)
        return

    if data.startswith("check_force:"):
        await check_force_callback(update, context)
        return

    if data.startswith("sub_info:"):
        await sub_info_callback(update, context)
        return

    await query.answer()

    if data == "force_rank":
        if not await active_required(update, context):
            return
        await query.message.reply_text(
            "🔇 <b>FORCE RANK</b>\n\n"
            "Reply pesan member dengan /forcerank\n"
            "atau /forcerank @username.",
            parse_mode="HTML",
        )

    elif data == "unforce_rank":
        if not await active_required(update, context):
            return
        await query.message.reply_text(
            "🔊 <b>UNFORCE</b>\n\n"
            "Reply pesan member dengan /unforcerank\n"
            "atau /unforcerank @username.",
            parse_mode="HTML",
        )

    elif data == "force_list":
        if not await active_required(update, context):
            return
        if not await admin_required(update, context):
            return
        rows = db.list_forced(query.message.chat.id)
        if not rows:
            await query.message.reply_text(
                "📋 Tidak ada member yang sedang Force Rank."
            )
            return
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
        if not await active_required(update, context):
            return
        await query.message.reply_text(
            "🔗 <b>LINK RANK</b>\n\n"
            "Admin grup dapat mengatur:\n"
            "<code>/setrank https://t.me/channel/9</code>",
            parse_mode="HTML",
        )

    elif data == "settings":
        if not await active_required(update, context):
            return
        await query.message.reply_text(
            "⚙️ <b>PENGATURAN</b>\n\n"
            "/setrank - link post rank\n"
            "/setsub - channel wajib subscribe\n"
            "/config - lihat konfigurasi",
            parse_mode="HTML",
        )

    elif data == "help":
        await query.message.reply_text(
            "❓ <b>BANTUAN</b>\n\n"
            "🔇 /forcerank - mute + wajib rank\n"
            "🔊 /unforcerank - buka mute\n"
            "📋 /forcelist - daftar Force Rank\n"
            "🔗 /setrank - atur post rank\n"
            "📢 /setsub - atur channel subscribe\n"
            "⚙️ /config - konfigurasi\n"
            "💰 /buy - beli akses",
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
# TRACK USERS
# ============================================================

async def track_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP, ChatType.PRIVATE):
        db.save_seen_user(
            chat.id,
            user.id,
            user.username,
            user.full_name,
        )


# ============================================================
# ERROR
# ============================================================

async def error_handler(update, context):
    logger.error(
        "Unhandled exception: %r",
        context.error,
        exc_info=(type(context.error), context.error, context.error.__traceback__)
        if context.error else None,
    )


# ============================================================
# MAIN
# ============================================================

def main():
    db.init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Public
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", start))
    app.add_handler(CommandHandler("buy", buy_command))
    app.add_handler(CommandHandler("status", status))

    # Owner
    app.add_handler(CommandHandler("aktif", aktif))
    app.add_handler(CommandHandler("nonaktif", nonaktif))
    app.add_handler(CommandHandler("users", daftar_user))

    # Force
    app.add_handler(CommandHandler("forcerank", forcerank))
    app.add_handler(CommandHandler("unforcerank", unforcerank))
    app.add_handler(CommandHandler("unforcer", unforcerank))
    app.add_handler(CommandHandler("forcelist", force_list))

    # Configuration
    app.add_handler(CommandHandler("setrank", setrank))
    app.add_handler(CommandHandler("setsub", setsub))
    app.add_handler(CommandHandler("config", config_info))

    # Specific callbacks MUST be before catch-all callback.
    app.add_handler(
        CallbackQueryHandler(
            check_force_callback,
            pattern=r"^check_force:-?\d+:\d+$",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            sub_info_callback,
            pattern=r"^sub_info:-?\d+:\d+$",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            buy_access_callback if False else menu_callback,
            pattern=r"^(buy_access|back_menu|force_rank|unforce_rank|force_list|link_rank|settings|help|owner_panel)$",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            buy_package_callback,
            pattern=r"^buy_(7d|30d|90d)$",
        )
    )

    # Rank comments: runs for messages in discussion groups.
    # It checks every forced record and matches the reply to the configured
    # channel post. This is the critical cross-chat fix.
    app.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS & ~filters.COMMAND,
            rank_comment_handler,
        ),
        group=0,
    )

    # Track users after rank detection.
    app.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND,
            track_user,
        ),
        group=1,
    )

    # Every 20 seconds, check subscription and finish any completed Force Rank.
    if app.job_queue:
        app.job_queue.run_repeating(
            periodic_force_check,
            interval=20,
            first=10,
            name="force_rank_periodic_check",
        )
    else:
        logger.warning(
            "JobQueue tidak tersedia. Pastikan requirements memakai python-telegram-bot[job-queue]."
        )

    app.add_error_handler(error_handler)

    logger.info("FORCE RANK BOT sedang berjalan...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=False,
    )


if __name__ == "__main__":
    main()
