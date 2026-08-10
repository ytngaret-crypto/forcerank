import os
import re
import html
import logging
from datetime import datetime, timedelta, timezone

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatPermissions
)

from telegram.constants import ChatMemberStatus

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    ContextTypes,
    filters
)

from database import (
    init_db,
    save_user,
    find_user_by_username,
    get_license,
    set_license,
    remove_license,
    get_all_licenses,
    save_group,
    get_group,
    set_rank_config,
    add_force_rank,
    get_force_rank,
    get_force_by_user,
    get_force_list,
    remove_force_rank
)


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

OWNER_ID = int(
    os.getenv("OWNER_ID", "0")
)
OWNER_ID_2 = int(os.getenv("OWNER_ID_2", "0") or 0)
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "").lstrip("@")

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN belum diisi."
    )

if not OWNER_ID:
    raise RuntimeError(
        "OWNER_ID belum diisi."
    )


# ============================================================
# LOG
# ============================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)

logger = logging.getLogger("FORCE-RANK")


# ============================================================
# TEMPORARY ACTIONS
# ============================================================

pending_actions = {}

# Format:
# pending_actions[user_id] = {
#     "action": "force",
#     "chat_id": -100xxx
# }


# ============================================================
# TEMPORARY MESSAGE CLEANUP
# ============================================================

async def delete_later(message, seconds=10):
    try:
        import asyncio
        await asyncio.sleep(seconds)
        await message.delete()
    except Exception:
        pass


def owner_contact_url():
    if OWNER_USERNAME:
        return f"https://t.me/{OWNER_USERNAME}"
    return None

# ============================================================
# BASIC
# ============================================================

def is_owner(user_id):
    return user_id in (OWNER_ID, OWNER_ID_2)


def mention(user):
    name = html.escape(
        user.full_name or "User"
    )

    return (
        f'<a href="tg://user?id={user.id}">'
        f'{name}</a>'
    )


def uname(user):
    if user.username:
        return "@" + html.escape(
            user.username
        )

    return "Tidak ada username"


def save_message_user(message):
    if not message:
        return

    if not message.from_user:
        return

    save_user(
        message.from_user.id,
        message.from_user.full_name,
        message.from_user.username
    )


# ============================================================
# LICENSE
# ============================================================

def license_active(user_id):

    if is_owner(user_id):
        return True

    row = get_license(user_id)

    if not row:
        return False

    try:
        expires = datetime.fromisoformat(
            row["expires_at"]
        )

        return (
            expires >
            datetime.now(timezone.utc)
        )

    except Exception:
        return False


def license_expiry(user_id):

    row = get_license(user_id)

    if not row:
        return None

    try:
        return datetime.fromisoformat(
            row["expires_at"]
        )

    except Exception:
        return None


async def require_license(
    update,
    context
):

    user = update.effective_user

    if not user:
        return False

    if is_owner(user.id):
        return True

    if license_active(user.id):
        return True

    message = update.effective_message

    if message:

        await message.reply_text(
            "🔒 <b>AKSES DITOLAK</b>\n\n"
            "Akun kamu belum memiliki "
            "lisensi aktif untuk menggunakan "
            "bot ini.\n\n"
            "Silakan hubungi owner bot "
            "untuk mendapatkan akses.",
            parse_mode="HTML"
        )

    return False


# ============================================================
# ADMIN
# ============================================================

async def is_admin(
    update,
    context
):

    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return False

    if is_owner(user.id):
        return True

    try:

        member = await context.bot.get_chat_member(
            chat.id,
            user.id
        )

        return member.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER
        )

    except Exception:

        return False


async def bot_is_admin(
    chat_id,
    context
):

    try:

        me = await context.bot.get_me()

        member = await context.bot.get_chat_member(
            chat_id,
            me.id
        )

        return member.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER
        )

    except Exception:

        return False


# ============================================================
# GROUP ACCESS
# ============================================================

async def group_access(
    update,
    context
):

    user = update.effective_user

    if not user:
        return False

    if is_owner(user.id):
        return True

    if not license_active(user.id):

        message = update.effective_message

        if message:

            await message.reply_text(
                "🔒 <b>BOT BELUM AKTIF UNTUK AKUN INI</b>\n\n"
                "Masa aktif akun kamu belum tersedia "
                "atau sudah habis.\n\n"
                "Hubungi owner bot.",
                parse_mode="HTML"
            )

        return False

    if not await is_admin(
        update,
        context
    ):

        message = update.effective_message

        if message:

            await message.reply_text(
                "❌ Kamu harus menjadi admin "
                "grup untuk mengatur Force Rank."
            )

        return False

    return True


# ============================================================
# PARSE RANK LINK
# ============================================================

def parse_rank_link(link):

    link = link.strip()

    patterns = [
        r"https?://t\.me/([A-Za-z0-9_]+)/(\d+)",
        r"https?://telegram\.me/([A-Za-z0-9_]+)/(\d+)"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            link
        )

        if match:

            channel = match.group(1)
            post_id = int(
                match.group(2)
            )

            return (
                link,
                channel,
                post_id
            )

    return None


# ============================================================
# MUTE
# ============================================================

async def mute_user(
    context,
    chat_id,
    user_id
):

    permissions = ChatPermissions(
        can_send_messages=False,
        can_send_audios=False,
        can_send_documents=False,
        can_send_photos=False,
        can_send_videos=False,
        can_send_video_notes=False,
        can_send_voice_notes=False,
        can_send_polls=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False
    )

    await context.bot.restrict_chat_member(
        chat_id,
        user_id,
        permissions=permissions
    )


# ============================================================
# UNMUTE
# ============================================================

async def unmute_user(
    context,
    chat_id,
    user_id
):

    permissions = ChatPermissions(
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
        can_invite_users=True
    )

    await context.bot.restrict_chat_member(
        chat_id,
        user_id,
        permissions=permissions
    )


# ============================================================
# MAIN MENU
# ============================================================

def main_menu(
    owner=False
):

    buttons = [
        [
            InlineKeyboardButton(
                "🔇 FORCE RANK",
                callback_data="force"
            ),
            InlineKeyboardButton(
                "🔊 UNFORCE",
                callback_data="unforce"
            )
        ],
        [
            InlineKeyboardButton("🔇 MUTE", callback_data="mute"),
            InlineKeyboardButton("🔊 UNMUTE", callback_data="unmute")
        ],
        [
            InlineKeyboardButton(
                "📋 DAFTAR FORCE",
                callback_data="list"
            )
        ],
        [
            InlineKeyboardButton(
                "🔗 LINK RANK",
                callback_data="rank"
            ),
            InlineKeyboardButton(
                "⚙️ PENGATURAN",
                callback_data="settings"
            )
        ],
        [
            InlineKeyboardButton(
                "❓ BANTUAN",
                callback_data="help"
            )
        ],
        [
            InlineKeyboardButton("💎 BUY AKSES PREMIUM", callback_data="buy_access")
        ]
    ]

    if owner:

        buttons.append([
            InlineKeyboardButton(
                "👑 OWNER PANEL",
                callback_data="owner"
            )
        ])

    return InlineKeyboardMarkup(
        buttons
    )


# ============================================================
# MENU COMMAND
# ============================================================

async def menu(
    update,
    context
):

    message = update.effective_message
    user = update.effective_user

    save_message_user(message)

    if message.chat.type in (
        "group",
        "supergroup"
    ):

        if not await group_access(
            update,
            context
        ):
            return

        save_group(
            message.chat.id,
            message.chat.title
        )

    await message.reply_text(
        "🕵️ <b>FORCE RANK BOT</b>\n\n"
        f"Halo {mention(user)}!\n\n"
        "Gunakan tombol di bawah "
        "agar tidak perlu mengetik command "
        "terus-menerus.",
        parse_mode="HTML",
        reply_markup=main_menu(
            is_owner(user.id)
        )
    )


# ============================================================
# START
# ============================================================

async def start(
    update,
    context
):

    message = update.effective_message
    user = update.effective_user

    save_message_user(message)

    expiry = license_expiry(
        user.id
    )

    if expiry:

        date_text = expiry.strftime(
            "%d-%m-%Y %H:%M"
        )

        status = (
            f"🟢 Aktif sampai: "
            f"{date_text} UTC"
        )

    else:

        status = "👑 Owner"

    await message.reply_text(
        "🤖 <b>FORCE RANK BOT</b>\n\n"
        f"{status}\n\n"
        "Klik menu untuk melanjutkan.",
        parse_mode="HTML",
        reply_markup=main_menu(
            is_owner(user.id)
        )
    )


# ============================================================
# FORCE RANK TARGET
# ============================================================

async def resolve_target(
    update,
    context
):

    message = update.effective_message
    chat = update.effective_chat

    # Reply
    if message.reply_to_message:

        user = (
            message
            .reply_to_message
            .from_user
        )

        if user:
            return user, None

    # Username / ID
    if not context.args:

        return None, (
            "❌ Target belum ditentukan.\n\n"
            "Reply pesan member lalu gunakan:\n"
            "<code>/forcerank</code>\n\n"
            "atau:\n"
            "<code>/forcerank @username</code>"
        )

    target = context.args[0]

    if target.isdigit():

        try:

            member = await context.bot.get_chat_member(
                chat.id,
                int(target)
            )

            return member.user, None

        except Exception:

            return None, (
                "❌ User ID tidak ditemukan."
            )

    row = find_user_by_username(
        target
    )

    if row:

        try:

            member = await context.bot.get_chat_member(
                chat.id,
                row["user_id"]
            )

            return member.user, None

        except Exception:
            pass

    return None, (
        "❌ Username belum dikenal bot.\n\n"
        "Cara paling aman: reply pesan "
        "member lalu gunakan command."
    )


# ============================================================
# FORCE RANK CORE
# ============================================================

async def do_force_rank(
    update,
    context,
    target
):

    message = update.effective_message
    chat = update.effective_chat
    admin = update.effective_user

    if not await bot_is_admin(
        chat.id,
        context
    ):

        await message.reply_text(
            "❌ Bot harus menjadi admin "
            "dan memiliki izin Restrict Members."
        )

        return

    try:

        member = await context.bot.get_chat_member(
            chat.id,
            target.id
        )

    except Exception:

        await message.reply_text(
            "❌ Member tidak ditemukan."
        )

        return

    if member.status in (
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER
    ):

        await message.reply_text(
            "❌ Admin/Owner tidak dapat "
            "di-Force Rank."
        )

        return

    if get_force_rank(
        chat.id,
        target.id
    ):

        await message.reply_text(
            f"⚠️ {mention(target)} "
            "sudah terkena Force Rank.",
            parse_mode="HTML"
        )

        return

    group = get_group(
        chat.id
    )

    if not group or not group["rank_link"]:

        await message.reply_text(
            "⚠️ Link rank belum disetting.\n\n"
            "Gunakan tombol:\n"
            "🔗 LINK RANK → SET LINK RANK"
        )

        return

    try:

        await mute_user(
            context,
            chat.id,
            target.id
        )

    except Exception:

        await message.reply_text(
            "❌ Gagal mute member.\n\n"
            "Pastikan bot memiliki izin "
            "<b>Restrict Members</b>.",
            parse_mode="HTML"
        )

        return

    save_user(
        target.id,
        target.full_name,
        target.username
    )

    add_force_rank(
        chat.id,
        target.id,
        target.full_name,
        target.username,
        admin.id
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📝 ISI RANK",
                url=group["rank_link"]
            )
        ],
        [
            InlineKeyboardButton(
                "🔄 CEK STATUS",
                callback_data=(
                    f"check:{chat.id}:{target.id}"
                )
            )
        ]
    ])

    await message.reply_text(
        "🔔 <b>FORCE RANK</b>\n\n"

        f"👤 User: {mention(target)}\n"
        f"🔹 Username: {uname(target)}\n\n"

        "🔇 Status: <b>MUTED</b>\n"
        "📝 Rank: <b>BELUM DIISI</b>\n"
        "Untuk membuka mute, user cukup mengisi rank "
        "pada postingan rank.\n\n"
        "Setelah komentar rank terdeteksi, bot akan "
        "otomatis melakukan unmute.",
        parse_mode="HTML",
        reply_markup=keyboard
    )


# ============================================================
# /FORCERANK
# ============================================================

async def forcerank(
    update,
    context
):

    if not await group_access(
        update,
        context
    ):
        return

    target, error = await resolve_target(
        update,
        context
    )

    if not target:

        await update.effective_message.reply_text(
            error,
            parse_mode="HTML"
        )

        return

    await do_force_rank(
        update,
        context,
        target
    )


# ============================================================
# /UNFORCERANK
# ============================================================

async def unforcerank(
    update,
    context
):

    if not await group_access(
        update,
        context
    ):
        return

    target, error = await resolve_target(
        update,
        context
    )

    if not target:

        await update.effective_message.reply_text(
            error,
            parse_mode="HTML"
        )

        return

    if not get_force_rank(
        update.effective_chat.id,
        target.id
    ):

        await update.effective_message.reply_text(
            "⚠️ User tersebut tidak sedang "
            "terkena Force Rank."
        )

        return

    try:

        await unmute_user(
            context,
            update.effective_chat.id,
            target.id
        )

    except Exception:

        await update.effective_message.reply_text(
            "❌ Gagal unmute."
        )

        return

    remove_force_rank(
        update.effective_chat.id,
        target.id
    )

    await update.effective_message.reply_text(
        "🔊 <b>FORCE RANK DIBUKA</b>\n\n"
        f"👤 {mention(target)}\n\n"
        "Status: <b>UNMUTED</b>",
        parse_mode="HTML"
    )


# ============================================================
# /MUTE
# ============================================================

async def mute_command(
    update,
    context
):

    if not await group_access(
        update,
        context
    ):
        return

    target, error = await resolve_target(
        update,
        context
    )

    if not target:

        await update.effective_message.reply_text(
            error,
            parse_mode="HTML"
        )

        return

    try:

        await mute_user(
            context,
            update.effective_chat.id,
            target.id
        )

        await update.effective_message.reply_text(
            "🔇 <b>MUTE BERHASIL</b>\n\n"
            f"👤 {mention(target)}",
            parse_mode="HTML"
        )

    except Exception:

        await update.effective_message.reply_text(
            "❌ Gagal mute."
        )


# ============================================================
# /UNMUTE
# ============================================================

async def unmute_command(
    update,
    context
):

    if not await group_access(
        update,
        context
    ):
        return

    target, error = await resolve_target(
        update,
        context
    )

    if not target:

        await update.effective_message.reply_text(
            error,
            parse_mode="HTML"
        )

        return

    try:

        await unmute_user(
            context,
            update.effective_chat.id,
            target.id
        )

        remove_force_rank(
            update.effective_chat.id,
            target.id
        )

        await update.effective_message.reply_text(
            "🔊 <b>UNMUTE BERHASIL</b>\n\n"
            f"👤 {mention(target)}",
            parse_mode="HTML"
        )

    except Exception:

        await update.effective_message.reply_text(
            "❌ Gagal unmute."
        )


# ============================================================
# FORCE LIST
# ============================================================

async def force_list(
    update,
    context
):

    if not await group_access(
        update,
        context
    ):
        return

    rows = get_force_list(
        update.effective_chat.id
    )

    if not rows:

        await update.effective_message.reply_text(
            "✅ Tidak ada member yang sedang "
            "terkena Force Rank."
        )

        return

    text = (
        "🔒 <b>FORCE RANK AKTIF</b>\n\n"
    )

    for i, row in enumerate(
        rows,
        1
    ):

        name = html.escape(
            row["name"] or "Unknown"
        )

        username = (
            "@" + html.escape(row["username"])
            if row["username"]
            else "Tanpa username"
        )

        text += (
            f"<b>{i}. {name}</b>\n"
            f"👤 {username}\n"
            f"🔇 MUTED\n\n"
        )

    await update.effective_message.reply_text(
        text,
        parse_mode="HTML"
    )


# ============================================================
# SET RANK
# ============================================================

async def set_rank_start(
    query,
    context
):

    chat_id = query.message.chat.id

    pending_actions[
        query.from_user.id
    ] = {
        "action": "set_rank",
        "chat_id": chat_id
    }

    await query.edit_message_text(
        "🔗 <b>SET LINK RANK</b>\n\n"
        "Kirim link postingan rank.\n\n"
        "Contoh:\n"
        "<code>https://t.me/abshsjjjv/9</code>\n\n"
        "Bot akan otomatis mengambil:\n"
        "• Channel\n"
        "• ID postingan\n"
        "• Link rank",
        parse_mode="HTML"
    )


# ============================================================
# CHECK SUBSCRIBE
# ============================================================

async def check_subscription(
    context,
    channel,
    user_id
):

    try:

        member = await context.bot.get_chat_member(
            "@" + channel,
            user_id
        )

        return member.status in (
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER
        )

    except Exception as e:

        logger.warning(
            "Subscription check error: %s",
            e
        )

        return False


# ============================================================
# DETECT RANK COMMENT
# ============================================================

def is_rank_comment(
    message,
    group_config
):

    if not message:
        return False

    root = message.reply_to_message

    if not root:
        return False

    if not group_config:
        return False

    channel = (
        group_config["rank_channel"]
        or ""
    ).lower()

    post_id = (
        group_config["rank_post_id"]
    )

    # ========================================================
    # FORWARD ORIGIN
    # ========================================================

    origin = getattr(
        root,
        "forward_origin",
        None
    )

    if origin:

        origin_chat = getattr(
            origin,
            "chat",
            None
        )

        origin_id = getattr(
            origin,
            "message_id",
            None
        )

        if origin_chat:

            username = (
                getattr(
                    origin_chat,
                    "username",
                    None
                )
                or ""
            ).lower()

            if (
                username == channel
                and origin_id == post_id
            ):

                return True

    # ========================================================
    # OLD FORWARD
    # ========================================================

    old_chat = getattr(
        root,
        "forward_from_chat",
        None
    )

    old_id = getattr(
        root,
        "forward_from_message_id",
        None
    )

    if old_chat:

        username = (
            getattr(
                old_chat,
                "username",
                None
            )
            or ""
        ).lower()

        if (
            username == channel
            and old_id == post_id
        ):

            return True

    # ========================================================
    # AUTOMATIC FORWARD FALLBACK
    # ========================================================

    if getattr(
        root,
        "is_automatic_forward",
        False
    ):

        sender_chat = getattr(
            root,
            "sender_chat",
            None
        )

        if sender_chat:

            username = (
                getattr(
                    sender_chat,
                    "username",
                    None
                )
                or ""
            ).lower()

            if username == channel:

                return True

    return False


# ============================================================
# PROCESS RANK
# ============================================================

async def process_rank(
    message,
    context,
    user_id=None
):
    """Rank saja adalah syarat. Begitu komentar rank valid terdeteksi,
    member langsung di-unmute dan admin/forced_by diberi notifikasi."""
    if not message or not message.from_user:
        return

    user = message.from_user
    if user_id and user.id != user_id:
        return

    rows = get_force_by_user(user.id)
    if not rows:
        return

    for row in rows:
        group_id = row["chat_id"]
        try:
            await unmute_user(context, group_id, user.id)
        except Exception as e:
            logger.error("AUTO UNMUTE ERROR: %s", e)
            continue

        forced_by = row["forced_by"]
        remove_force_rank(group_id, user.id)

        group_text = (
            "🔔 <b>FORCE RANK SELESAI</b>\\n\\n"
            f"👤 User: {mention(user)}\\n"
            f"🔹 Username: {uname(user)}\\n\\n"
            "📝 Rank: <b>SUDAH DIISI</b>\\n"
            "🔊 Status: <b>AUTO UNMUTE</b>\\n\\n"
            "🎉 Rank berhasil terdeteksi. Member telah di-unmute otomatis."
        )
        try:
            await context.bot.send_message(group_id, group_text, parse_mode="HTML")
        except Exception:
            pass

        admin_text = (
            "🔔 <b>FORCE RANK SELESAI</b>\\n\\n"
            f"👤 User: {mention(user)}\\n"
            f"🔹 Username: {uname(user)}\\n\\n"
            "📝 Rank: ✅ Sudah diisi\\n"
            "🔊 Status: ✅ Auto unmute"
        )
        try:
            await context.bot.send_message(forced_by, admin_text, parse_mode="HTML")
        except Exception:
            pass

        try:
            await message.reply_text(
                "✅ <b>RANK TERDETEKSI</b>\\n\\n"
                "📝 Rank: ✅\\n"
                "🔊 Kamu telah di-unmute otomatis.\\n\\n"
                "🎉 Selamat datang kembali!",
                parse_mode="HTML"
            )
        except Exception:
            pass


# ============================================================
# CALLBACK MENU
# ============================================================

async def callback_handler(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    user = query.from_user
    data = query.data

    # ========================================================
    # CHECK STATUS
    # ========================================================

    if data.startswith("check:"):
        parts = data.split(":")
        group_id = int(parts[1])
        user_id = int(parts[2])

        if user.id != user_id:
            await query.answer("❌ Tombol ini bukan untuk kamu.", show_alert=True)
            return

        row = get_force_rank(group_id, user_id)
        if not row:
            await query.answer("✅ Kamu sudah tidak terkena Force Rank.", show_alert=True)
            return

        await query.answer("ℹ️ Bot menunggu komentar rank. Setelah terdeteksi, unmute otomatis.", show_alert=True)
        return

    # ========================================================
    # BUY PREMIUM — BOLEH DIAKSES SEMUA USER
    # ========================================================

    if data == "buy_access":
        rows = [
            [InlineKeyboardButton("🟢 7 HARI — Rp7.000", callback_data="buy:7:7000")],
            [InlineKeyboardButton("🔵 20 HARI — Rp20.000", callback_data="buy:20:20000")],
            [InlineKeyboardButton("🟣 30 HARI — Rp27.000", callback_data="buy:30:27000")],
            [InlineKeyboardButton("🔙 MENU", callback_data="back")]
        ]
        await query.edit_message_text(
            "💎 <b>BUY AKSES PREMIUM</b>\n\n"
            "Pilih masa aktif bot kamu:\n\n"
            "🟢 7 hari — <b>Rp7.000</b>\n"
            "🔵 20 hari — <b>Rp20.000</b>\n"
            "🟣 30 hari — <b>Rp27.000</b>\n\n"
            "Setelah pembayaran dikonfirmasi, owner mengaktifkan akses berdasarkan username Telegram kamu.",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows)
        )
        return

    if data.startswith("buy:"):
        _, days, price = data.split(":")
        username = user.username or "Tidak ada username"
        text = (
            "🛒 <b>PERMINTAAN AKSES PREMIUM</b>\n\n"
            f"👤 User: {mention(user)}\n"
            f"🔹 Username: @{html.escape(username) if username != 'Tidak ada username' else '-'}\n"
            f"📦 Paket: {days} hari\n"
            f"💰 Harga: Rp{int(price):,}".replace(",", ".") + "\n\n"
            "Silakan hubungi owner untuk pembayaran. Setelah dikonfirmasi, owner akan menjalankan /aktif."
        )
        rows = []
        if owner_contact_url():
            rows.append([InlineKeyboardButton("👑 HUBUNGI OWNER", url=owner_contact_url())])
        rows.append([InlineKeyboardButton("🔙 KEMBALI", callback_data="buy_access")])
        # notify owners automatically when possible
        for oid in (OWNER_ID, OWNER_ID_2):
            if oid:
                try:
                    await context.bot.send_message(oid, text, parse_mode="HTML")
                except Exception:
                    pass
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))
        return

    # ========================================================
    # LICENSE CHECK
    # ========================================================

    if not is_owner(user.id):

        if not license_active(user.id):

            await query.answer(
                "🔒 Lisensi kamu tidak aktif.",
                show_alert=True
            )

            return

    # ========================================================
    # FORCE
    # ========================================================

    if data == "force":

        if not await is_admin(
            update,
            context
        ):

            await query.answer(
                "❌ Hanya admin.",
                show_alert=True
            )

            return

        pending_actions[user.id] = {
            "action": "force",
            "chat_id": query.message.chat.id
        }

        await query.edit_message_text(
            "🔇 <b>FORCE RANK</b>\n\n"
            "Sekarang <b>reply pesan member</b> "
            "yang ingin di-Force Rank.\n\n"
            "Setelah reply, bot akan otomatis "
            "memprosesnya.\n\n"
            "❌ Jangan mengetik command.",
            parse_mode="HTML"
        )

        return

    # ========================================================
    # UNFORCE
    # ========================================================

    if data == "unforce":

        if not await is_admin(
            update,
            context
        ):
            return

        pending_actions[user.id] = {
            "action": "unforce",
            "chat_id": query.message.chat.id
        }

        await query.edit_message_text(
            "🔊 <b>UNFORCE RANK</b>\n\n"
            "Reply pesan member yang ingin "
            "dibuka Force Rank-nya.",
            parse_mode="HTML"
        )

        return

    # ========================================================
    # MUTE / UNMUTE MENU
    # ========================================================

    if data in ("mute", "unmute"):
        if not await is_admin(update, context):
            await query.answer("❌ Hanya admin.", show_alert=True)
            return
        pending_actions[user.id] = {"action": data, "chat_id": query.message.chat.id}
        label = "MUTE" if data == "mute" else "UNMUTE"
        await query.edit_message_text(
            f"{'🔇' if data == 'mute' else '🔊'} <b>{label}</b>\n\nReply pesan member yang ingin di-{label.lower()}.",
            parse_mode="HTML"
        )
        return

    # ========================================================
    # LIST
    # ========================================================

    if data == "list":

        rows = get_force_list(
            query.message.chat.id
        )

        if not rows:

            await query.edit_message_text(
                "📋 <b>FORCE RANK</b>\n\n"
                "Tidak ada member yang sedang "
                "terkena Force Rank.",
                parse_mode="HTML"
            )

            return

        text = (
            "📋 <b>FORCE RANK AKTIF</b>\n\n"
        )

        for i, row in enumerate(
            rows,
            1
        ):

            name = html.escape(
                row["name"] or "Unknown"
            )

            text += (
                f"{i}. {name}\n"
                "🔇 MUTED\n\n"
            )

        await query.edit_message_text(
            text,
            parse_mode="HTML"
        )

        return

    # ========================================================
    # RANK
    # ========================================================

    if data == "rank":

        group = get_group(
            query.message.chat.id
        )

        if group and group["rank_link"]:

            await query.edit_message_text(
                "🔗 <b>LINK RANK</b>\n\n"
                f"{html.escape(group['rank_link'])}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "📝 BUKA RANK",
                            url=group["rank_link"]
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "⚙️ GANTI LINK",
                            callback_data="setrank"
                        )
                    ]
                ])
            )

        else:

            await query.edit_message_text(
                "🔗 <b>LINK RANK BELUM DIATUR</b>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "➕ SET LINK RANK",
                            callback_data="setrank"
                        )
                    ]
                ])
            )

        return

    # ========================================================
    # DIRECT MUTE / UNMUTE
    # ========================================================

    if action["action"] in ("mute", "unmute"):
        if message.chat.id != action["chat_id"] or not message.reply_to_message:
            return
        target = message.reply_to_message.from_user
        if not target:
            return
        pending_actions.pop(user.id, None)
        try:
            if action["action"] == "mute":
                await mute_user(context, message.chat.id, target.id)
                await message.reply_text(f"🔇 <b>MUTE BERHASIL</b>\n\n👤 {mention(target)}", parse_mode="HTML")
            else:
                await unmute_user(context, message.chat.id, target.id)
                remove_force_rank(message.chat.id, target.id)
                await message.reply_text(f"🔊 <b>UNMUTE BERHASIL</b>\n\n👤 {mention(target)}", parse_mode="HTML")
        except Exception:
            await message.reply_text("❌ Gagal mengubah status mute.")
        return

    # ========================================================
    # SET RANK
    # ========================================================

    if data == "setrank":

        await set_rank_start(
            query,
            context
        )

        return

    # ========================================================
    # SETTINGS
    # ========================================================

    if data == "settings":

        await query.edit_message_text(
            "⚙️ <b>PENGATURAN</b>\n\n"
            "Pilih pengaturan:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔗 Set Link Rank",
                        callback_data="setrank"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "📋 Status Rank",
                        callback_data="rank"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⬅️ Menu",
                        callback_data="back"
                    )
                ]
            ])
        )

        return

    # ========================================================
    # HELP
    # ========================================================

    if data == "help":

        await query.edit_message_text(
            "❓ <b>BANTUAN</b>\n\n"

            "🔇 <b>Force Rank</b>\n"
            "Member dimute sampai memenuhi "
            "persyaratan.\n\n"

            "📝 <b>Rank</b>\n"
            "Member harus berkomentar pada post rank.\n\n"
            "🔊 Setelah rank terdeteksi, bot otomatis unmute.\n\n"

            "Admin tetap dapat menggunakan:\n"
            "/forcerank\n"
            "/unforcerank\n"
            "/mute\n"
            "/unmute\n"
            "/forceranklist",
            parse_mode="HTML"
        )

        return

    # ========================================================
    # OWNER
    # ========================================================

    if data == "owner":

        if not is_owner(user.id):
            return

        await query.edit_message_text(
            "👑 <b>OWNER PANEL</b>\n\n"
            "Gunakan command owner:\n\n"

            "<code>/aktif 30d @username</code>\n"
            "<code>/nonaktif @username</code>\n"
            "<code>/cek @username</code>\n"
            "<code>/pelanggan</code>\n\n"

            "Owner dapat mengatur masa aktif "
            "pelanggan dari sini.",
            parse_mode="HTML"
        )

        return

    # ========================================================
    # BACK
    # ========================================================

    if data == "back":

        await query.edit_message_text(
            "🕵️ <b>FORCE RANK BOT</b>\n\n"
            "Pilih menu:",
            parse_mode="HTML",
            reply_markup=main_menu(
                is_owner(user.id)
            )
        )


# ============================================================
# PENDING ACTION MESSAGE
# ============================================================

async def pending_message(
    update,
    context
):

    message = update.effective_message
    user = update.effective_user

    if not message:
        return

    if not message.from_user:
        return

    action = pending_actions.get(
        user.id
    )

    if not action:
        return

    # Hanya proses pesan user yang punya pending
    # dan jangan ganggu komentar rank.
    if action["action"] in (
        "force",
        "unforce"
    ):

        if not message.reply_to_message:

            return

        if message.chat.id != action["chat_id"]:

            return

        target = message.reply_to_message.from_user

        if not target:
            return

        pending_actions.pop(
            user.id,
            None
        )

        if action["action"] == "force":

            await do_force_rank(
                update,
                context,
                target
            )

        elif action["action"] == "unforce":

            row = get_force_rank(
                message.chat.id,
                target.id
            )

            if not row:

                await message.reply_text(
                    "⚠️ User tersebut tidak "
                    "sedang terkena Force Rank."
                )

                return

            try:

                await unmute_user(
                    context,
                    message.chat.id,
                    target.id
                )

                remove_force_rank(
                    message.chat.id,
                    target.id
                )

                await message.reply_text(
                    "🔊 <b>FORCE RANK DIBUKA</b>\n\n"
                    f"👤 {mention(target)}",
                    parse_mode="HTML"
                )

            except Exception:

                await message.reply_text(
                    "❌ Gagal unmute."
                )

        return

    # ========================================================
    # SET RANK
    # ========================================================

    if action["action"] == "set_rank":

        if message.chat.id != action["chat_id"]:
            return

        if not await is_admin(
            update,
            context
        ):
            return

        parsed = parse_rank_link(
            message.text or ""
        )

        if not parsed:

            await message.reply_text(
                "❌ Link tidak valid.\n\n"
                "Contoh:\n"
                "https://t.me/abshsjjjv/9"
            )

            return

        link, channel, post_id = parsed

        set_rank_config(
            message.chat.id,
            link,
            channel,
            post_id
        )

        pending_actions.pop(
            user.id,
            None
        )

        try:
            await message.delete()
        except Exception:
            pass

        success = await update.effective_chat.send_message(
            "✅ <b>LINK RANK BERHASIL DISIMPAN</b>\n\n"
            f"🔗 {html.escape(link)}\n"
            f"📢 Channel rank: @{html.escape(channel)}\n"
            f"📝 Post: {post_id}\n\n"
            "📝 Syarat Force Rank sekarang cukup isi rank.\n"
            "Pesan ini akan dihapus otomatis dalam 10 detik.",
            parse_mode="HTML"
        )
        import asyncio
        asyncio.create_task(delete_later(success, 10))


# ============================================================
# RANK COMMENT HANDLER
# ============================================================

async def comment_handler(
    update,
    context
):
    message = update.effective_message
    if not message or not message.from_user:
        return
    if message.chat.type not in ("group", "supergroup"):
        return

    # Komentar rank berada di linked discussion group, bukan di grup utama.
    # Karena itu cari konfigurasi berdasarkan semua Force Rank milik user.
    rows = get_force_by_user(message.from_user.id)
    if not rows:
        return

    for row in rows:
        group = get_group(row["chat_id"])
        if not group or not group["rank_link"]:
            continue

        try:
            rank_chat = await context.bot.get_chat("@" + group["rank_channel"])
            linked_id = getattr(rank_chat, "linked_chat_id", None)
            if linked_id and linked_id == message.chat.id and is_rank_comment(message, group):
                logger.info("RANK COMMENT VALID user=%s group=%s", message.from_user.id, row["chat_id"])
                await process_rank(message, context, message.from_user.id)
                return
        except Exception as e:
            logger.warning("Rank discussion check failed: %s", e)


# ============================================================
# /AKTIF OWNER
# ============================================================

def parse_duration(text):

    match = re.fullmatch(
        r"(\d+)([dhm])",
        text.lower().strip()
    )

    if not match:
        return None

    amount = int(
        match.group(1)
    )

    unit = match.group(2)

    if unit == "d":
        return timedelta(
            days=amount
        )

    if unit == "h":
        return timedelta(
            hours=amount
        )

    if unit == "m":
        return timedelta(
            minutes=amount
        )

    return None


async def activate_license(
    update,
    context
):

    if not is_owner(
        update.effective_user.id
    ):

        await update.effective_message.reply_text(
            "❌ Command ini khusus owner."
        )

        return

    if len(context.args) < 2:

        await update.effective_message.reply_text(
            "Format:\n\n"
            "<code>/aktif 30d @username</code>\n\n"
            "Contoh:\n"
            "<code>/aktif 30d @alceea</code>",
            parse_mode="HTML"
        )

        return

    duration = parse_duration(
        context.args[0]
    )

    if not duration:

        await update.effective_message.reply_text(
            "❌ Format durasi salah.\n\n"
            "Gunakan contoh:\n"
            "30d\n"
            "7d\n"
            "24h"
        )

        return

    target_text = context.args[1]

    # Username dari database
    row = find_user_by_username(
        target_text
    )

    # Kalau reply user, prioritaskan reply
    if update.effective_message.reply_to_message:

        target = (
            update.effective_message
            .reply_to_message
            .from_user
        )

        target_id = target.id
        target_username = target.username

    elif row:

        target_id = row["user_id"]
        target_username = row["username"]

    else:

        await update.effective_message.reply_text(
            "❌ Username belum dikenal bot.\n\n"
            "User tersebut harus pernah "
            "berinteraksi dengan bot terlebih dahulu.\n\n"
            "Cara paling mudah: minta pembeli "
            "buka bot dan tekan /start, lalu ulangi "
            "command ini."
        )

        return

    old = get_license(
        target_id
    )

    now_utc = datetime.now(
        timezone.utc
    )

    # Kalau masih aktif, tambah dari tanggal expired lama
    if old:

        try:

            old_expiry = datetime.fromisoformat(
                old["expires_at"]
            )

            if old_expiry > now_utc:
                expiry = (
                    old_expiry
                    + duration
                )
            else:
                expiry = (
                    now_utc
                    + duration
                )

        except Exception:

            expiry = now_utc + duration

    else:

        expiry = now_utc + duration

    set_license(
        target_id,
        target_username,
        expiry.isoformat()
    )

    await update.effective_message.reply_text(
        "✅ <b>AKUN BERHASIL DIAKTIFKAN</b>\n\n"
        f"👤 User ID: <code>{target_id}</code>\n"
        f"🔹 Username: @{html.escape(target_username or '-')} \n"
        f"⏳ Durasi: <b>{context.args[0]}</b>\n"
        f"📅 Berakhir: <b>{expiry.strftime('%d-%m-%Y %H:%M UTC')}</b>\n\n"
        "Sekarang pelanggan dapat "
        "menambahkan bot ke grupnya "
        "dan menggunakannya sebagai admin.",
        parse_mode="HTML"
    )


# ============================================================
# /NONAKTIF
# ============================================================

async def deactivate_license(
    update,
    context
):

    if not is_owner(
        update.effective_user.id
    ):
        return

    if not context.args:

        await update.effective_message.reply_text(
            "Gunakan:\n"
            "<code>/nonaktif @username</code>",
            parse_mode="HTML"
        )

        return

    row = find_user_by_username(
        context.args[0]
    )

    if not row:

        await update.effective_message.reply_text(
            "❌ Username tidak ditemukan."
        )

        return

    remove_license(
        row["user_id"]
    )

    await update.effective_message.reply_text(
        "❌ <b>AKUN DINONAKTIFKAN</b>\n\n"
        f"👤 @{html.escape(row['username'] or '-')}",
        parse_mode="HTML"
    )


# ============================================================
# /CEK
# ============================================================

async def check_license_command(
    update,
    context
):

    if not is_owner(
        update.effective_user.id
    ):
        return

    if not context.args:

        await update.effective_message.reply_text(
            "Gunakan:\n"
            "<code>/cek @username</code>",
            parse_mode="HTML"
        )

        return

    row = find_user_by_username(
        context.args[0]
    )

    if not row:

        await update.effective_message.reply_text(
            "❌ User tidak ditemukan."
        )

        return

    license_row = get_license(
        row["user_id"]
    )

    if not license_row:

        await update.effective_message.reply_text(
            "🔴 <b>TIDAK AKTIF</b>",
            parse_mode="HTML"
        )

        return

    try:

        expiry = datetime.fromisoformat(
            license_row["expires_at"]
        )

        active = (
            expiry >
            datetime.now(timezone.utc)
        )

    except Exception:

        active = False
        expiry = None

    if active:

        await update.effective_message.reply_text(
            "🟢 <b>AKUN AKTIF</b>\n\n"
            f"👤 @{html.escape(row['username'] or '-')}\n"
            f"📅 Berakhir: "
            f"{expiry.strftime('%d-%m-%Y %H:%M UTC')}",
            parse_mode="HTML"
        )

    else:

        await update.effective_message.reply_text(
            "🔴 <b>AKUN EXPIRED</b>\n\n"
            f"👤 @{html.escape(row['username'] or '-')}",
            parse_mode="HTML"
        )


# ============================================================
# /PELANGGAN
# ============================================================

async def customers(
    update,
    context
):

    if not is_owner(
        update.effective_user.id
    ):
        return

    rows = get_all_licenses()

    if not rows:

        await update.effective_message.reply_text(
            "📋 Belum ada pelanggan."
        )

        return

    text = (
        "👑 <b>DAFTAR PELANGGAN</b>\n\n"
    )

    now_utc = datetime.now(
        timezone.utc
    )

    for i, row in enumerate(
        rows,
        1
    ):

        try:

            expiry = datetime.fromisoformat(
                row["expires_at"]
            )

            active = expiry > now_utc

        except Exception:

            active = False
            expiry = None

        status = "🟢" if active else "🔴"

        text += (
            f"{i}. {status} "
            f"@{html.escape(row['username'] or '-')}\n"
        )

        if expiry:

            text += (
                f"   ⏰ {expiry.strftime('%d-%m-%Y %H:%M UTC')}\n"
            )

        text += "\n"

    await update.effective_message.reply_text(
        text,
        parse_mode="HTML"
    )


# ============================================================
# BOT ADDED / REMOVED
# ============================================================

async def bot_membership(
    update,
    context
):

    data = update.my_chat_member

    if not data:
        return

    chat = data.chat
    actor = data.from_user
    new_status = data.new_chat_member.status

    if new_status in (
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR
    ):

        save_group(
            chat.id,
            chat.title
        )

        if not is_owner(actor.id) and not license_active(actor.id):

            try:

                await context.bot.send_message(
                    chat.id,
                    "🔒 <b>BOT BELUM AKTIF</b>\n\n"
                    f"👤 Ditambahkan oleh: {mention(actor)}\n\n"
                    "Akun tersebut belum memiliki "
                    "lisensi aktif.\n\n"
                    "Hubungi owner bot untuk membeli "
                    "akses.",
                    parse_mode="HTML"
                )

            except Exception:
                pass

        else:

            try:

                await context.bot.send_message(
                    chat.id,
                    "🤖 <b>FORCE RANK BOT AKTIF</b>\n\n"
                    "Gunakan /menu untuk membuka "
                    "panel tombol.\n\n"
                    "Jangan lupa set link rank "
                    "terlebih dahulu.",
                    parse_mode="HTML"
                )

            except Exception:
                pass


# ============================================================
# AUTO TRACK USER
# ============================================================

async def track_all(
    update,
    context
):

    message = update.effective_message

    if not message:
        return

    save_message_user(
        message
    )


# ============================================================
# ERROR
# ============================================================

async def error_handler(
    update,
    context
):

    logger.exception(
        "BOT ERROR",
        exc_info=context.error
    )


# ============================================================
# MAIN
# ============================================================

def main():

    init_db()

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )

    # ========================================================
    # COMMAND
    # ========================================================

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "menu",
            menu
        )
    )

    app.add_handler(
        CommandHandler(
            "forcerank",
            forcerank
        )
    )

    app.add_handler(
        CommandHandler(
            "unforcerank",
            unforcerank
        )
    )

    app.add_handler(
        CommandHandler(
            "mute",
            mute_command
        )
    )

    app.add_handler(
        CommandHandler(
            "unmute",
            unmute_command
        )
    )

    app.add_handler(
        CommandHandler(
            "forceranklist",
            force_list
        )
    )

    # OWNER
    app.add_handler(
        CommandHandler(
            "aktif",
            activate_license
        )
    )

    app.add_handler(
        CommandHandler(
            "nonaktif",
            deactivate_license
        )
    )

    app.add_handler(
        CommandHandler(
            "cek",
            check_license_command
        )
    )

    app.add_handler(
        CommandHandler(
            "pelanggan",
            customers
        )
    )

    # ========================================================
    # CALLBACK
    # ========================================================

    app.add_handler(
        CallbackQueryHandler(
            callback_handler
        )
    )

    # ========================================================
    # BOT MEMBER STATUS
    # ========================================================

    app.add_handler(
        ChatMemberHandler(
            bot_membership,
            ChatMemberHandler.MY_CHAT_MEMBER
        )
    )

    # ========================================================
    # PENDING ACTIONS
    # ========================================================

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            pending_message
        ),
        group=0
    )

    # ========================================================
    # RANK COMMENTS
    # ========================================================

    app.add_handler(
        MessageHandler(
            filters.ALL,
            comment_handler
        ),
        group=1
    )

    # ========================================================
    # TRACK USERS
    # ========================================================

    app.add_handler(
        MessageHandler(
            filters.ALL,
            track_all
        ),
        group=2
    )

    app.add_error_handler(
        error_handler
    )

    logger.info(
        "======================================"
    )

    logger.info(
        "🤖 FORCE RANK BOT ONLINE"
    )

    logger.info(
        "OWNER ID: %s",
        OWNER_ID
    )

    logger.info(
        "======================================"
    )

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
